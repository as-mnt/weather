package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
)

func handler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var payload struct {
		Text string `json:"text"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		log.Printf("❌ Invalid JSON: %v", err)
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if payload.Text == "" {
		log.Println("❌ Empty 'text' field in request")
		http.Error(w, "Missing 'text' field", http.StatusBadRequest)
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
	msg := map[string]string{
		"chat_id": chatID,
		"text":    payload.Text,
	}
	body, _ := json.Marshal(msg)

	log.Printf("📡 Sending to Telegram: chat_id=%s, text=%.50s...", chatID, payload.Text)

	resp, err := http.Post(telegramURL, "application/json", bytes.NewBuffer(body))
	if err != nil {
		log.Printf("❌ Failed to connect to Telegram API: %v", err)
		http.Error(w, "Failed to send", http.StatusInternalServerError)
		return
	}
	defer resp.Body.Close()

	// Читаем тело ответа для логирования
	respBody, _ := io.ReadAll(resp.Body)

	// Логируем статус и тело
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
	log.Printf("🚀 Telegram proxy listening on :%s", port)
	http.HandleFunc("/alert", handler)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
