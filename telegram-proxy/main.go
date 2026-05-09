package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"
)

type Alert struct {
	Status      string            `json:"status"`
	Labels      map[string]string `json:"labels"`
	Annotations map[string]string `json:"annotations"`
}

type AlertManagerWebhook struct {
	Receiver string  `json:"receiver"`
	Status   string  `json:"status"`
	Alerts   []Alert `json:"alerts"`
}

func formatMessage(alert Alert, payloadStatus string) string {
	var text string
	if summary := alert.Annotations["summary"]; summary != "" {
		text = summary
	} else if desc := alert.Annotations["description"]; desc != "" {
		text = desc
	} else {
		name := alert.Labels["alertname"]
		if name == "" {
			name = "UnknownAlert"
		}
		text = fmt.Sprintf("Alert: %s", name)
	}
	if payloadStatus == "resolved" {
		return "✅ RESOLVED\n" + text
	}
	return "🚨 FIRING\n" + text
}

func handler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if secret := os.Getenv("TG_PROXY_WEBHOOK_SECRET"); secret != "" {
		if r.Header.Get("Authorization") != "Bearer "+secret {
			log.Printf("❌ Unauthorized request from %s", r.RemoteAddr)
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
	}

	var payload AlertManagerWebhook
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		log.Printf("❌ Invalid JSON: %v", err)
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if len(payload.Alerts) == 0 {
		log.Println("❌ No alerts in payload")
		http.Error(w, "No alerts", http.StatusBadRequest)
		return
	}

	botToken := os.Getenv("BOT_TOKEN")
	chatID := os.Getenv("CHAT_ID")

	if botToken == "" {
		log.Println("❌ BOT_TOKEN is not set")
		http.Error(w, "BOT_TOKEN not configured", http.StatusInternalServerError)
		return
	}
	if chatID == "" {
		log.Println("❌ CHAT_ID is not set")
		http.Error(w, "CHAT_ID not configured", http.StatusInternalServerError)
		return
	}

	telegramURL := "https://api.telegram.org/bot" + botToken + "/sendMessage"
	client := &http.Client{Timeout: 10 * time.Second}

	for _, alert := range payload.Alerts {
		message := formatMessage(alert, payload.Status)
		log.Printf("📡 Sending to Telegram: %.100s...", message)

		msg := map[string]string{"chat_id": chatID, "text": message}
		body, _ := json.Marshal(msg)

		resp, err := client.Post(telegramURL, "application/json", bytes.NewBuffer(body))
		if err != nil {
			log.Printf("❌ Failed to connect to Telegram API: %v", err)
			http.Error(w, "Failed to send", http.StatusInternalServerError)
			return
		}
		respBody, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		log.Printf("⬅️ Telegram response: status=%d, body=%.200s", resp.StatusCode, string(respBody))

		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			log.Printf("❌ Telegram API error: %s", string(respBody))
			http.Error(w, "Telegram API error", http.StatusInternalServerError)
			return
		}
		log.Println("✅ Message sent successfully to Telegram")
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	log.Printf("🚀 Telegram proxy for Alertmanager listening on :%s", port)
	http.HandleFunc("/alert", handler)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
