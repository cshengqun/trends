package main

import (
	"net/http"
	"strings"
)

func (s server) earningsForecast(w http.ResponseWriter, r *http.Request) {
	s.query(w, r, `WITH upcoming AS (
		SELECT DISTINCT ON (f.period_type, f.period_end, f.metric_id) f.*
		FROM earnings_forecasts f
		WHERE f.entity_id = $1 AND $2 AND f.captured_at <= now()
		  AND f.period_end >= (now() AT TIME ZONE 'Asia/Shanghai')::date - interval '6 months'
		  AND NOT EXISTS (
			SELECT 1 FROM observations o WHERE o.entity_id = f.entity_id
			  AND o.metric_id = f.metric_id AND o.period_end = f.period_end
			  AND o.quality_status = 'verified' AND o.available_at <= now()
			  AND (o.period_type = f.period_type OR o.period_type = 'annual'
			       OR (f.period_type = 'annual' AND o.period_type = 'quarterly'))
		  )
		ORDER BY f.period_type, f.period_end, f.metric_id, (f.method <> 'consensus'), f.captured_at DESC
	), next_period AS (
		SELECT period_type, period_end FROM upcoming
		ORDER BY period_end, CASE period_type WHEN 'quarterly' THEN 1 WHEN 'semiannual' THEN 2 ELSE 3 END
		LIMIT 1
	)
	SELECT jsonb_build_object('points', coalesce((
		SELECT jsonb_agg((to_jsonb(u) - 'entity_id') || jsonb_build_object(
			'growth', CASE WHEN prior_value > 0 THEN round(100 * (value / prior_value - 1), 6) END
		) ORDER BY metric_id DESC)
		FROM upcoming u JOIN next_period USING (period_type, period_end)
	), '[]'::jsonb))
	WHERE EXISTS (SELECT 1 FROM entities WHERE id = $1)`,
		strings.ToUpper(r.PathValue("id")), s.official)
}
