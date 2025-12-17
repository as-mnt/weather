package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
)

// AlertManagerWebhook — структура входящего вебхука от Alertmanager
type AlertManagerWebhook struct {
	Receiver string `json:"receiver"`
	Status   string `json:"status"`
	Alerts   []struct {
		Status      string            `json:"status"`
		Labels      map[string]string `json:"labels"`
		Annotations map[string]string `json:"annotations"`
	} `json:"alerts"`
}

func handler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
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

	// Берём первую алерту (обычно их одна при тестировании)
	alert := payload.Alerts[0]

	// Формируем текст сообщения
	var message string
	if summary := alert.Annotations["summary"]; summary != "" {
		message = summary
	} else if desc := alert.Annotations["description"]; desc != "" {
		message = desc
	} else {
		name := alert.Labels["alertname"]
		if name == "" {
			name = "UnknownAlert"
		}
		message = fmt.Sprintf("🚨 Alert: %s", name)
	}

	// Добавим статус (firing/resolved)
	if payload.Status == "resolved" {
		message = "✅ RESOLVED\n" + message
	} else {
		message = "🚨 FIRING\n" + message
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
	msg := map[string]string{
		"chat_id": chatID,
		"text":    message,
	}
	body, _ := json.Marshal(msg)

	log.Printf("📡 Sending to Telegram: %.100s...", message)

	resp, err := http.Post(telegramURL, "application/json", bytes.NewBuffer(body))
	if err != nil {
		log.Printf("❌ Failed to connect to Telegram API: %v", err)
		http.Error(w, "Failed to send", http.StatusInternalServerError)
		return
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)
	log.Printf("⬅️ Telegram response: status=%d, body=%.200s", resp.StatusCode, string(respBody))

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		log.Println("✅ Message sent successfully to Telegram")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	} else {
		log.Printf("❌ Telegram API error: %s", string(respBody))
		http.Error(w, "Telegram API error", http.StatusInternalServerError)
	}
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
