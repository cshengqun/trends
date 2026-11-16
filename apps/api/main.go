package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type server struct {
	db       *pgxpool.Pool
	official bool
}

func (s server) dataKind() string {
	if s.official {
		return "official"
	}
	return "mock"
}

func (s server) quality() string {
	if s.official {
		return "verified"
	}
	return "mock"
}

type envelope struct {
	Data  any       `json:"data,omitempty"`
	Error *apiError `json:"error,omitempty"`
}

type apiError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func send(w http.ResponseWriter, status int, body envelope) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(body); err != nil {
		log.Printf("encode response: %v", err)
	}
}

func fail(w http.ResponseWriter, status int, code, message string) {
	send(w, status, envelope{Error: &apiError{Code: code, Message: message}})
}

func (s server) query(w http.ResponseWriter, r *http.Request, query string, args ...any) {
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	var data json.RawMessage
	err := s.db.QueryRow(ctx, query, args...).Scan(&data)
	switch {
	case errors.Is(err, pgx.ErrNoRows), err == nil && string(data) == "null":
		fail(w, 404, "not_found", "没有找到对应的记录")
	case err != nil:
		log.Printf("query %s: %v", r.URL.Path, err)
		fail(w, 503, "data_unavailable", "数据服务暂时不可用")
	default:
		send(w, 200, envelope{Data: data})
	}
}

func pagination(q url.Values) (int, int, bool) {
	limit, offset := 30, 0
	var err error
	if q.Has("limit") {
		limit, err = strconv.Atoi(q.Get("limit"))
		if err != nil || limit < 1 || limit > 100 {
			return 0, 0, false
		}
	}
	if q.Has("offset") {
		offset, err = strconv.Atoi(q.Get("offset"))
		if err != nil || offset < 0 || offset > 1000000 {
			return 0, 0, false
		}
	}
	return limit, offset, true
}

const entityProjection = `
	SELECT e.*, latest.period_end AS latest_period, latest.data_updated_at
	FROM entities e
	LEFT JOIN LATERAL (
		SELECT max(period_end) AS period_end, max(available_at) AS data_updated_at
		FROM observations WHERE quality_status=$1 AND entity_id = e.id AND available_at <= now()
	) latest ON true
`

func (s server) entities(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	limit, offset, ok := pagination(q)
	market := q.Get("market")
	search := strings.TrimSpace(q.Get("q"))
	if !ok || len(search) > 120 || (market != "" && market != "HK" && market != "CN") {
		fail(w, 400, "invalid_query", "搜索、市场或分页参数无效")
		return
	}
	s.query(w, r, `SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.symbol), '[]') FROM (`+entityProjection+`
		WHERE kind = 'stock' AND latest.period_end IS NOT NULL
		AND ($2 = '' OR strpos(lower(name), lower($2)) > 0 OR strpos(lower(symbol), lower($2)) > 0
			OR (market='HK' AND ltrim(split_part(lower(symbol),'.',1),'0') =
				ltrim(regexp_replace(lower($2),'\.hk$',''),'0')))
		AND ($3 = '' OR market = $3) ORDER BY symbol LIMIT $4 OFFSET $5
	) t`, s.quality(), search, market, limit, offset)
}

func (s server) entity(w http.ResponseWriter, r *http.Request) {
	s.query(w, r, `SELECT to_jsonb(t) || jsonb_build_object('latest_metrics', (
		SELECT coalesce(jsonb_agg(to_jsonb(metric) ORDER BY display_order), '[]') FROM (
			SELECT DISTINCT ON (o.metric_id) o.metric_id, m.name, m.category, m.display_order,
				o.value, o.unit, o.currency, o.period_end, o.period_type
			FROM observations o JOIN metrics m ON m.id=o.metric_id
			JOIN sources origin ON origin.id=o.source_id
			WHERE o.entity_id=t.id AND o.quality_status=$1 AND o.available_at <= now()
			ORDER BY o.metric_id, CASE o.period_type WHEN 'monthly' THEN 1 WHEN 'quarterly' THEN 2 ELSE 3 END,
				o.period_end DESC, (origin.kind <> 'official'), o.revision DESC
		) metric
	), 'available_series', (
		SELECT coalesce(jsonb_agg(to_jsonb(series) ORDER BY metric_id, period_type), '[]') FROM (
			SELECT DISTINCT o.metric_id, o.period_type FROM observations o
			WHERE o.entity_id=t.id AND o.quality_status=$1 AND o.available_at <= now()
		) series
	)) FROM (`+entityProjection+` WHERE e.id = $2 AND latest.period_end IS NOT NULL) t`,
		s.quality(), strings.ToUpper(r.PathValue("id")))
}

func (s server) metrics(w http.ResponseWriter, r *http.Request) {
	s.query(w, r, `SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY display_order), '[]') FROM metrics m
		WHERE EXISTS (SELECT 1 FROM observations WHERE metric_id=m.id AND quality_status=$1 AND available_at<=now())`, s.quality())
}

const observationProjection = `
	SELECT o.id, o.entity_id, o.metric_id, m.name AS metric_name, o.period_start, o.period_end,
	       o.period_type, o.published_at, o.available_at, o.value, o.currency, o.unit, o.source_id,
	       o.calculation_version, o.quality_status, o.revision, s.kind AS source_kind,
	       s.label AS source_label, s.document_ref, s.raw_payload->>'market_date' AS market_date,
	       coalesce(s.raw_payload->'supporting_documents', '[]'::jsonb) AS supporting_documents
	FROM observations o JOIN sources s ON s.id=o.source_id JOIN metrics m ON m.id=o.metric_id
`

func (s server) series(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	entity, metric, period := strings.ToUpper(q.Get("entity_id")), q.Get("metric_id"), q.Get("period")
	if period == "" {
		period = "annual"
	}
	if entity == "" || metric == "" || len(entity) > 80 || len(metric) > 80 ||
		(period != "annual" && period != "quarterly" && period != "monthly") {
		fail(w, 400, "invalid_query", "请指定公司、指标及有效的财务期间")
		return
	}
	s.query(w, r, `SELECT CASE WHEN
		EXISTS (SELECT 1 FROM entities WHERE id=$1) AND EXISTS (SELECT 1 FROM metrics WHERE id=$2)
		THEN coalesce((SELECT jsonb_agg(to_jsonb(t) ORDER BY period_end) FROM (`+observationProjection+`
			JOIN (SELECT DISTINCT ON (period_end) o2.id FROM observations o2 JOIN sources origin ON origin.id=o2.source_id
			      WHERE entity_id=$1 AND metric_id=$2 AND period_type=$3 AND quality_status=$4 AND available_at <= now()
			      ORDER BY period_end, (origin.kind <> 'official'), revision DESC) latest ON latest.id=o.id
		) t), '[]') END`, entity, metric, period, s.quality())
}

func (s server) quarterlyDashboard(w http.ResponseWriter, r *http.Request) {
	s.query(w, r, `WITH quarter_window AS (
		SELECT (date_trunc('quarter', now() AT TIME ZONE 'Asia/Shanghai')::date - 1) AS end_date
	), selected AS (
		SELECT DISTINCT ON (metric_id, period_end) o.id
		FROM observations o JOIN sources origin ON origin.id=o.source_id CROSS JOIN quarter_window
		WHERE entity_id=$1 AND quality_status=$2 AND period_type='quarterly' AND available_at<=now()
		  AND metric_id IN ('revenue','net_income','pe_ttm','dividend_yield')
		  AND period_end > end_date - interval '4 years' AND period_end <= end_date
		ORDER BY metric_id, period_end, (origin.kind <> 'official'), revision DESC
	), base AS (`+observationProjection+` JOIN selected ON o.id=selected.id), points AS (
		SELECT to_jsonb(b) AS point, b.metric_id, b.period_end FROM base b
		UNION ALL
		SELECT to_jsonb(b) || jsonb_build_object(
			'metric_id', growth.metric_id, 'metric_name', definition.name, 'unit', '%', 'currency', '',
			'value', round(100 * (b.value / prior.value - 1), 6),
			'available_at', greatest(b.available_at, prior.available_at),
			'supporting_documents', b.supporting_documents ||
				jsonb_build_array(jsonb_build_object('label', prior.source_label, 'url', prior.document_ref)) ||
				prior.supporting_documents
		), growth.metric_id, b.period_end
		FROM base b JOIN base prior ON prior.metric_id=b.metric_id
			AND prior.period_end + interval '1 year'=b.period_end
			AND prior.currency=b.currency AND prior.unit=b.unit AND prior.value>0
		JOIN (VALUES ('revenue','revenue_growth'), ('net_income','profit_growth')) growth(base_id,metric_id)
			ON growth.base_id=b.metric_id
		JOIN metrics definition ON definition.id=growth.metric_id
	)
	SELECT jsonb_build_object('end_date', end_date, 'points',
		coalesce((SELECT jsonb_agg(point ORDER BY period_end, metric_id) FROM points
			WHERE period_end > quarter_window.end_date - interval '3 years'), '[]'))
	FROM quarter_window WHERE EXISTS (SELECT 1 FROM entities WHERE id=$1)`,
		strings.ToUpper(r.PathValue("id")), s.quality())
}

const insightProjection = `
	SELECT i.*, e.name AS entity_name, e.symbol, m.name AS metric_name, m.unit AS metric_unit,
		(SELECT max(o.available_at) FROM insight_evidence ie JOIN observations o ON o.id=ie.observation_id
		 WHERE ie.insight_id=i.id) AS data_updated_at,
		coalesce((
			SELECT jsonb_agg(jsonb_build_object('period_end',period_end,'value',value) ORDER BY period_end)
			FROM (
				SELECT o.period_end, o.value FROM insight_evidence ie JOIN observations o ON o.id=ie.observation_id
				WHERE ie.insight_id=i.id AND o.metric_id=i.metric_id
				ORDER BY o.period_end DESC LIMIT 10
			) history
		), '[]') AS spark
	FROM insights i JOIN entities e ON e.id=i.entity_id JOIN metrics m ON m.id=i.metric_id
`

func (s server) insights(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	category, entity := q.Get("category"), strings.ToUpper(q.Get("entity_id"))
	limit, offset, ok := pagination(q)
	switch category {
	case "", "growth", "profitability", "cash_flow", "financial_health", "valuation", "operations":
	default:
		ok = false
	}
	if !ok || len(entity) > 80 {
		fail(w, 400, "invalid_query", "分类、公司或分页参数无效")
		return
	}
	s.query(w, r, `SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY rule_id, symbol, id), '[]') FROM (`+insightProjection+`
		WHERE ($1 = '' OR i.category=$1) AND ($2 = '' OR i.entity_id=$2) AND i.data_kind=$5
		ORDER BY rule_id, symbol, i.id LIMIT $3 OFFSET $4
	) t`, category, entity, limit, offset, s.dataKind())
}

func (s server) insight(w http.ResponseWriter, r *http.Request) {
	s.query(w, r, `SELECT to_jsonb(t) FROM (`+insightProjection+` WHERE i.id=$1 AND i.data_kind=$2) t`,
		r.PathValue("id"), s.dataKind())
}

func (s server) evidence(w http.ResponseWriter, r *http.Request) {
	s.query(w, r, `SELECT CASE WHEN EXISTS (SELECT 1 FROM insights WHERE id=$1 AND data_kind=$2) THEN
		coalesce((SELECT jsonb_agg(to_jsonb(t) ORDER BY period_end, metric_id) FROM (`+observationProjection+`
		JOIN insight_evidence ie ON ie.observation_id=o.id WHERE ie.insight_id=$1
	) t), '[]') END`, r.PathValue("id"), s.dataKind())
}

func (s server) overview(w http.ResponseWriter, r *http.Request) {
	s.query(w, r, `WITH published AS (
		SELECT entity_id, period_end, available_at FROM observations WHERE quality_status=$1 AND available_at<=now()
	) SELECT jsonb_build_object(
		'company_count', (SELECT count(DISTINCT entity_id) FROM published),
		'insight_count', (SELECT count(*) FROM insights WHERE data_kind=$2),
		'latest_period', (SELECT max(period_end) FROM published),
		'last_updated_at', (SELECT max(available_at) FROM published),
		'market_count', (SELECT count(DISTINCT market) FROM entities WHERE id IN (SELECT entity_id FROM published)),
		'data_kind', $2::text
	)`, s.quality(), s.dataKind())
}

func (s server) health(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()
	var ready bool
	err := s.db.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM data_ingestion_runs WHERE status='success')
		AND EXISTS (SELECT 1 FROM observations WHERE quality_status=$1 AND available_at<=now())`, s.quality()).Scan(&ready)
	if err != nil || !ready {
		fail(w, 503, "not_ready", "数据库或当前数据集尚未就绪")
		return
	}
	send(w, 200, envelope{Data: map[string]string{"status": "ok", "database": "postgresql", "data_kind": s.dataKind()}})
}

func (s server) routes(web http.Handler, basePath string) http.Handler {
	mux := http.NewServeMux()
	api := basePath + "/api"
	mux.HandleFunc("GET "+api+"/v1/health", s.health)
	mux.HandleFunc("GET "+api+"/v1/overview", s.overview)
	mux.HandleFunc("GET "+api+"/v1/entities", s.entities)
	mux.HandleFunc("GET "+api+"/v1/entities/{id}", s.entity)
	mux.HandleFunc("GET "+api+"/v1/entities/{id}/quarterly", s.quarterlyDashboard)
	mux.HandleFunc("GET "+api+"/v1/metrics", s.metrics)
	mux.HandleFunc("GET "+api+"/v1/series", s.series)
	mux.HandleFunc("GET "+api+"/v1/insights", s.insights)
	mux.HandleFunc("GET "+api+"/v1/insights/{id}", s.insight)
	mux.HandleFunc("GET "+api+"/v1/insights/{id}/evidence", s.evidence)
	mux.HandleFunc(api+"/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			w.Header().Set("Allow", "GET, HEAD")
			fail(w, 405, "method_not_allowed", "接口仅支持读取")
			return
		}
		fail(w, 404, "not_found", "没有找到对应的接口")
	})
	if web != nil {
		mux.Handle("/", web)
	}
	return mux
}

func main() {
	mode := os.Getenv("TRENDS_DATA_MODE")
	if mode != "" && mode != "official" && mode != "mock" {
		log.Fatal("TRENDS_DATA_MODE must be mock or official")
	}
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		log.Fatal("DATABASE_URL is required")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		log.Fatal("could not configure PostgreSQL connection")
	}
	defer pool.Close()

	var web http.Handler
	if origin := os.Getenv("WEB_ORIGIN"); origin != "" {
		target, err := url.Parse(origin)
		if err != nil || (target.Scheme != "http" && target.Scheme != "https") || target.Host == "" {
			log.Fatal("WEB_ORIGIN must be an absolute HTTP URL")
		}
		proxy := httputil.NewSingleHostReverseProxy(target)
		proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
			log.Printf("web upstream: %v", err)
			http.Error(w, "Frontend temporarily unavailable", http.StatusBadGateway)
		}
		web = proxy
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	app := &http.Server{
		Addr: ":" + port, Handler: (server{db: pool, official: mode == "official"}).routes(web, os.Getenv("NEXT_PUBLIC_BASE_PATH")),
		ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 60 * time.Second,
	}
	log.Printf("Trends listening on port %s", port)
	log.Fatal(app.ListenAndServe())
}
