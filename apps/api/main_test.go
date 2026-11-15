package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestQueryValidationAndRouting(t *testing.T) {
	web := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	})
	for _, tc := range []struct {
		method string
		path   string
		status int
		code   string
	}{
		{"GET", "/", 204, ""},
		{"GET", "/stocks/0700.HK", 204, ""},
		{"GET", "/api/v1/entities?limit=101", 400, "invalid_query"},
		{"GET", "/api/v1/entities?market=US", 400, "invalid_query"},
		{"GET", "/api/v1/series?entity_id=0700.HK&metric_id=revenue&period=daily", 400, "invalid_query"},
		{"GET", "/api/v1/series", 400, "invalid_query"},
		{"GET", "/api/v1/insights?offset=-1", 400, "invalid_query"},
		{"GET", "/api/v1/insights?category=other", 400, "invalid_query"},
		{"GET", "/api/v1/missing", 404, "not_found"},
		{"POST", "/api/v1/entities", 405, "method_not_allowed"},
	} {
		for _, basePath := range []string{"", "/trends"} {
			path := basePath + tc.path
			t.Run(tc.method+" "+path, func(t *testing.T) {
				response := httptest.NewRecorder()
				(server{}).routes(web, basePath).ServeHTTP(response, httptest.NewRequest(tc.method, path, nil))
				if response.Code != tc.status {
					t.Fatalf("status = %d, want %d", response.Code, tc.status)
				}
				if tc.code != "" {
					var body envelope
					if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil || body.Error == nil || body.Error.Code != tc.code {
						t.Fatalf("unexpected error payload: %s", response.Body.String())
					}
				}
			})
		}
	}
}
