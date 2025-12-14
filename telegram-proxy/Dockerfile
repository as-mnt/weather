# ------------------------------------------------------------
# telegram-proxy — лёгкий HTTP-прокси для отправки алертов в Telegram
# Размер финального образа: ~6 МБ
# ------------------------------------------------------------

# Этап 1: сборка бинарника
FROM golang:1.23-alpine AS builder

# Устанавливаем git (иногда требуется для go mod)
RUN apk add --no-cache git

WORKDIR /app

# Копируем go mod и sum (для кэширования зависимостей)
#COPY go.mod go.sum ./
COPY go.mod ./

# Загружаем зависимости
RUN go mod download

# Копируем исходный код
COPY main.go .

# Собираем статически, без CGO — для минимального размера
RUN CGO_ENABLED=0 GOOS=linux go build -a -ldflags '-extldflags "-static"' -o telegram-proxy .


# Этап 2: финальный образ
FROM alpine:latest

# Устанавливаем только корневые сертификаты для HTTPS
RUN apk --no-cache add ca-certificates

WORKDIR /root/

# Копируем бинарник из этапа сборки
COPY --from=builder /app/telegram-proxy .

# Порт, на котором слушает прокси
EXPOSE 8080

# Запуск
CMD ["./telegram-proxy"]
