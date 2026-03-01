# =============================================================================
# Weather Monitoring Project — Makefile
# =============================================================================

# Настройки по умолчанию
#NAMESPACE      ?= monitoring
NAMESPACE      ?= default
IMAGE_REPO     ?= asmnt/weather
IMAGE_TAG      ?= dev-$(shell git rev-parse --short HEAD)
#IMAGE_TAG      ?= latest
CHART_PATH     ?= ./charts/weather
SECRETS_FILE   ?= .secrets/secrets.env
TELEGRAM_SECRETS_FILE   ?= .secrets/secrets-telegram.env

# Пути к файлам (настройте под вашу структуру)
APP_MAIN       ?= app/mkweathergraphs_loop.py
CONFIG_SOURCE  ?= public/index.html     # файл, который будет в ConfigMap
CONFIGMAP_NAME ?= weather-config

# Цвета
GREEN  := $(shell tput setaf 2)
RESET  := $(shell tput sgr0)

.PHONY: help build push deploy deploy-local secrets test sync-config logs describe undeploy

help:
	@echo "Доступные команды:"
	@echo "  make build            — собрать Docker-образ локально"
	@echo "  make push             — собрать и запушить образ"
	@echo "  make secrets          — создать Secret из .secrets/secrets.env"
	@echo "  make sync-config      — обновить ConfigMap из $(CONFIG_SOURCE)"
	@echo "  make test             — проверить синтаксис и импорты Python-скрипта"
	@echo "  make deploy           — задеплоить с IMAGE_TAG"
	@echo "  make deploy-local     — задеплоить с тегом dev-<sha>"
	@echo "  make logs             — показать логи"
	@echo "  make describe         — описать Deployment"
	@echo "  make undeploy         — удалить релиз и секреты"
	@echo ""
	@echo "Примеры:"
	@echo "  make sync-config CONFIG_SOURCE=public/custom.html"
	@echo "  make test APP_MAIN=app/my_script.py"

# Проверка зависимостей
check-env:
	@which kubectl > /dev/null || (echo "❌ kubectl не установлен"; exit 1)
	@which helm > /dev/null || (echo "❌ helm не установлен"; exit 1)
	@kubectl cluster-info > /dev/null || (echo "❌ kubectl не настроен"; exit 1)

# Сборка
build:
	docker build -t $(IMAGE_REPO):$(IMAGE_TAG) .

push: build
	docker push $(IMAGE_REPO):$(IMAGE_TAG)

# Секреты
secrets:
	@if [ ! -f "$(SECRETS_FILE)" ]; then \
		echo "❌ Файл секретов не найден: $(SECRETS_FILE)"; \
		echo "Создайте его на основе scripts/env.example"; \
		exit 1; \
	fi
	@echo "$(GREEN)📦 Создаём Secret 'weather-secrets' в namespace '$(NAMESPACE)'$(RESET)"
	kubectl delete secret weather-secrets --namespace "$(NAMESPACE)" --ignore-not-found
	kubectl create secret generic weather-secrets \
		--namespace "$(NAMESPACE)" \
		--from-env-file="$(SECRETS_FILE)"
	
	@echo "$(GREEN)📦 Создаём Secret 'telegram-credentials' в namespace '$(NAMESPACE)'$(RESET)"
	kubectl delete secret telegram-credentials --namespace "$(NAMESPACE)" --ignore-not-found
	kubectl create secret generic telegram-credentials \
    --namespace "$(NAMESPACE)" \
    --from-env-file="$(TELEGRAM_SECRETS_FILE)"
#  --from-literal=BOT_TOKEN="123456:ABC..." \
#  --from-literal=CHAT_ID="-1001234567890"

# Обновление ConfigMap из файла
sync-config:
	@if [ ! -f "$(CONFIG_SOURCE)" ]; then \
		echo "❌ Файл конфигурации не найден: $(CONFIG_SOURCE)"; \
		exit 1; \
	fi
	@echo "$(GREEN)🔄 Обновляем ConfigMap '$(CONFIGMAP_NAME)' из $(CONFIG_SOURCE)$(RESET)"
	kubectl create configmap $(CONFIGMAP_NAME) \
		--namespace "$(NAMESPACE)" \
		--from-file=$(CONFIG_SOURCE) \
		--dry-run=client -o yaml | kubectl apply -f -

# Запуск базовых тестов (проверка синтаксиса и импортов)
test:
	@if [ ! -f "$(APP_MAIN)" ]; then \
		echo "❌ Основной скрипт не найден: $(APP_MAIN)"; \
		exit 1; \
	fi
	@echo "$(GREEN)🧪 Запуск тестов для $(APP_MAIN)$(RESET)"
	python -m py_compile $(APP_MAIN)
	@echo "$(GREEN)✅ Синтаксис корректен$(RESET)"

# Деплой
deploy-local: check-env
	IMAGE_TAG ?= dev-$(shell git rev-parse --short HEAD)
	helm upgrade --install weather $(CHART_PATH) \
		--namespace "$(NAMESPACE)" \
		--create-namespace \
		--set image.tag="$(IMAGE_TAG)" \
		--wait

deploy: check-env
	helm upgrade --install weather $(CHART_PATH) \
		--namespace "$(NAMESPACE)" \
		--create-namespace \
		--set image.tag="$(IMAGE_TAG)" \
		--wait


	helm upgrade --install telegraf \
		--namespace "$(NAMESPACE)" \
	  influxdata/telegraf -f infra/telegraf/values-meteo.yaml

	@echo "$(GREEN)🔧 Применяем DNS-патч к telegraf для изоляции от fvds.ru$(RESET)"
	kubectl patch deployment telegraf -n "$(NAMESPACE)" --type=json -p="$$(cat infra/telegraf/dns-patch.json)"

	@echo "$(GREEN)🔄 Перезапускаем telegraf для применения изменений$(RESET)"
	kubectl rollout restart deployment/telegraf -n "$(NAMESPACE)"


# Отладка
logs:
	kubectl logs -l app.kubernetes.io/name=weather -n "$(NAMESPACE)" --tail=100 -f

describe:
	kubectl describe deployment weather -n "$(NAMESPACE)"

# Очистка
undeploy:
	helm uninstall weather --namespace "$(NAMESPACE)"
	kubectl delete secret weather-secrets --namespace "$(NAMESPACE)" --ignore-not-found
	kubectl delete configmap $(CONFIGMAP_NAME) --namespace "$(NAMESPACE)" --ignore-not-found
	helm uninstall telegraf --namespace "$(NAMESPACE)"

# === Telegram Proxy ===
PROXY_IMAGE_REPO ?= asmnt/telegram-proxy
PROXY_IMAGE_TAG  ?= dev-$(shell git rev-parse --short HEAD)

build-proxy:
	docker build -t $(PROXY_IMAGE_REPO):$(PROXY_IMAGE_TAG) ./telegram-proxy

push-proxy: build-proxy
	docker push $(PROXY_IMAGE_REPO):$(PROXY_IMAGE_TAG)

undeploy-proxy:
	helm uninstall telegram-proxy --namespace "$(NAMESPACE)"

deploy-proxy:
	helm upgrade --install telegram-proxy ./charts/telegram-proxy \
		--namespace "$(NAMESPACE)" \
		--set image.tag="$(PROXY_IMAGE_TAG)" \
		--wait

proxy-logs:
	kubectl logs deploy/telegram-proxy -n "$(NAMESPACE)" --tail=100 -f

deploy-all: deploy deploy-proxy


# Prometheus
deploy-prometheus:
	kubectl apply -n "$(NAMESPACE)" -f infra/prometheus/weather-alerts-configmap.yaml
	helm upgrade --install prometheus prometheus-community/prometheus \
		-n "$(NAMESPACE)" \
		--create-namespace \
		-f infra/prometheus/values.yaml
	helm upgrade --install prometheus-blackbox-exporter prometheus-community/prometheus-blackbox-exporter \
		-n "$(NAMESPACE)" \
		-f infra/prometheus/blackbox-values.yaml

undeploy-prometheus:
	helm uninstall prometheus --namespace "$(NAMESPACE)"
	helm uninstall prometheus-blackbox-exporter --namespace "$(NAMESPACE)"

deploy-monitoring: deploy-telegraf deploy-prometheus
