package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

// --- formatMessage ---

func TestFormatMessage(t *testing.T) {
	tests := []struct {
		name          string
		alert         Alert
		payloadStatus string
		wantPrefix    string
		wantContains  string
	}{
		{
			name:          "firing uses summary over description",
			alert:         Alert{Annotations: map[string]string{"summary": "disk full", "description": "ignored"}},
			payloadStatus: "firing",
			wantPrefix:    "🚨 FIRING\n",
			wantContains:  "disk full",
		},
		{
			name:          "firing falls back to description",
			alert:         Alert{Annotations: map[string]string{"description": "cpu high"}},
			payloadStatus: "firing",
			wantPrefix:    "🚨 FIRING\n",
			wantContains:  "cpu high",
		},
		{
			name:          "firing falls back to alertname",
			alert:         Alert{Labels: map[string]string{"alertname": "CPUHigh"}, Annotations: map[string]string{}},
			payloadStatus: "firing",
			wantPrefix:    "🚨 FIRING\n",
			wantContains:  "CPUHigh",
		},
		{
			name:          "firing with no labels or annotations uses UnknownAlert",
			alert:         Alert{Labels: map[string]string{}, Annotations: map[string]string{}},
			payloadStatus: "firing",
			wantPrefix:    "🚨 FIRING\n",
			wantContains:  "UnknownAlert",
		},
		{
			name:          "resolved prefixes with checkmark",
			alert:         Alert{Annotations: map[string]string{"summary": "disk ok"}},
			payloadStatus: "resolved",
			wantPrefix:    "✅ RESOLVED\n",
			wantContains:  "disk ok",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := formatMessage(tt.alert, tt.payloadStatus)
			if !strings.HasPrefix(got, tt.wantPrefix) {
				t.Errorf("prefix: got %q, want prefix %q", got, tt.wantPrefix)
			}
			if !strings.Contains(got, tt.wantContains) {
				t.Errorf("content: %q does not contain %q", got, tt.wantContains)
			}
		})
	}
}

// --- handler helpers ---

func makePayload(status string, alerts ...Alert) string {
	p := AlertManagerWebhook{Receiver: "test", Status: status, Alerts: alerts}
	b, _ := json.Marshal(p)
	return string(b)
}

func singleAlert() Alert {
	return Alert{
		Labels:      map[string]string{"alertname": "TestAlert"},
		Annotations: map[string]string{"summary": "something went wrong"},
	}
}

func postRequest(body string) *http.Request {
	return httptest.NewRequest(http.MethodPost, "/alert", strings.NewReader(body))
}

// fakeTelegram starts a test server that responds with the given status code to all requests.
// It also counts how many times it was called.
func fakeTelegram(t *testing.T, statusCode int) (serverURL string, callCount func() int32) {
	t.Helper()
	var n int32
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&n, 1)
		w.WriteHeader(statusCode)
		w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(func() {
		ts.Close()
		telegramBaseURL = "https://api.telegram.org"
	})
	telegramBaseURL = ts.URL
	return ts.URL, func() int32 { return atomic.LoadInt32(&n) }
}

// --- handler tests ---

func TestHandler_MethodNotAllowed(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/alert", nil)
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Errorf("got %d, want 405", rr.Code)
	}
}

func TestHandler_AuthMissingHeader_Returns401(t *testing.T) {
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "secret123")
	req := postRequest(makePayload("firing", singleAlert()))
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Errorf("got %d, want 401", rr.Code)
	}
}

func TestHandler_AuthWrongToken_Returns401(t *testing.T) {
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "secret123")
	req := postRequest(makePayload("firing", singleAlert()))
	req.Header.Set("Authorization", "Bearer wrongtoken")
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Errorf("got %d, want 401", rr.Code)
	}
}

func TestHandler_AuthCorrectToken_PassesAuth(t *testing.T) {
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "secret123")
	t.Setenv("BOT_TOKEN", "")
	req := postRequest(makePayload("firing", singleAlert()))
	req.Header.Set("Authorization", "Bearer secret123")
	rr := httptest.NewRecorder()
	handler(rr, req)
	// Auth passed; fails at BOT_TOKEN check, not auth
	if rr.Code == http.StatusUnauthorized {
		t.Error("got 401 but correct token should pass auth")
	}
}

func TestHandler_AuthDisabledWhenSecretEmpty(t *testing.T) {
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "")
	t.Setenv("BOT_TOKEN", "")
	req := postRequest(makePayload("firing", singleAlert()))
	rr := httptest.NewRecorder()
	handler(rr, req)
	// No auth check when secret is unset; request proceeds to BOT_TOKEN check
	if rr.Code == http.StatusUnauthorized {
		t.Error("got 401 but auth should be disabled when secret is empty")
	}
}

func TestHandler_InvalidJSON_Returns400(t *testing.T) {
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "")
	req := postRequest("{invalid json")
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Errorf("got %d, want 400", rr.Code)
	}
}

func TestHandler_EmptyAlerts_Returns400(t *testing.T) {
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "")
	body := makePayload("firing") // no alerts
	req := postRequest(body)
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Errorf("got %d, want 400", rr.Code)
	}
}

func TestHandler_MissingBotToken_Returns500(t *testing.T) {
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "")
	t.Setenv("BOT_TOKEN", "")
	t.Setenv("CHAT_ID", "-123")
	req := postRequest(makePayload("firing", singleAlert()))
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusInternalServerError {
		t.Errorf("got %d, want 500", rr.Code)
	}
}

func TestHandler_MissingChatID_Returns500(t *testing.T) {
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "")
	t.Setenv("BOT_TOKEN", "mytoken")
	t.Setenv("CHAT_ID", "")
	req := postRequest(makePayload("firing", singleAlert()))
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusInternalServerError {
		t.Errorf("got %d, want 500", rr.Code)
	}
}

func TestHandler_TelegramAPIError_Returns500(t *testing.T) {
	fakeTelegram(t, http.StatusInternalServerError)
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "")
	t.Setenv("BOT_TOKEN", "mytoken")
	t.Setenv("CHAT_ID", "-123")
	req := postRequest(makePayload("firing", singleAlert()))
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusInternalServerError {
		t.Errorf("got %d, want 500", rr.Code)
	}
}

func TestHandler_Success_Returns200(t *testing.T) {
	_, calls := fakeTelegram(t, http.StatusOK)
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "")
	t.Setenv("BOT_TOKEN", "mytoken")
	t.Setenv("CHAT_ID", "-123")
	req := postRequest(makePayload("firing", singleAlert()))
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusOK {
		t.Errorf("got %d, want 200", rr.Code)
	}
	if strings.TrimSpace(rr.Body.String()) != "OK" {
		t.Errorf("body: got %q, want \"OK\"", rr.Body.String())
	}
	if calls() != 1 {
		t.Errorf("Telegram called %d times, want 1", calls())
	}
}

func TestHandler_MultipleAlerts_AllSent(t *testing.T) {
	_, calls := fakeTelegram(t, http.StatusOK)
	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "")
	t.Setenv("BOT_TOKEN", "mytoken")
	t.Setenv("CHAT_ID", "-123")
	a1 := Alert{Labels: map[string]string{"alertname": "A1"}, Annotations: map[string]string{"summary": "first"}}
	a2 := Alert{Labels: map[string]string{"alertname": "A2"}, Annotations: map[string]string{"summary": "second"}}
	req := postRequest(makePayload("firing", a1, a2))
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusOK {
		t.Errorf("got %d, want 200", rr.Code)
	}
	if calls() != 2 {
		t.Errorf("Telegram called %d times, want 2", calls())
	}
}

func TestHandler_MultipleAlerts_PartialFailureReturns500AfterSecondSend(t *testing.T) {
	var n int32
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callNum := atomic.AddInt32(&n, 1)
		if callNum == 1 {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{"ok":true}`))
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"ok":false}`))
	}))
	t.Cleanup(func() {
		ts.Close()
		telegramBaseURL = "https://api.telegram.org"
	})
	telegramBaseURL = ts.URL

	t.Setenv("TG_PROXY_WEBHOOK_SECRET", "")
	t.Setenv("BOT_TOKEN", "mytoken")
	t.Setenv("CHAT_ID", "-123")
	a1 := Alert{Labels: map[string]string{"alertname": "A1"}, Annotations: map[string]string{"summary": "first"}}
	a2 := Alert{Labels: map[string]string{"alertname": "A2"}, Annotations: map[string]string{"summary": "second"}}
	req := postRequest(makePayload("firing", a1, a2))
	rr := httptest.NewRecorder()
	handler(rr, req)

	if rr.Code != http.StatusInternalServerError {
		t.Errorf("got %d, want 500", rr.Code)
	}
	if atomic.LoadInt32(&n) != 2 {
		t.Errorf("Telegram called %d times, want 2", atomic.LoadInt32(&n))
	}
}
