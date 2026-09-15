---
title: Пользовательские голосовые провайдеры
description: Обзор пользовательских голосовых провайдеров Beacon
---

# Пользовательские голосовые провайдеры

Beacon может загружать пользовательские голосовые провайдеры на Python для self-hosted установок.

Голосовой провайдер — это Python-модуль, который умеет совершать телефонный вызов через API конкретного провайдера: Mango, Voximplant, Zadarma, шлюз Asterisk, внутреннюю PBX или любой другой сервис.

Самому Beacon не нужно знать специфические детали API провайдера. Он загружает ваш модуль провайдера и взаимодействует с ним через стабильный провайдерский API.

## Поддерживаемые возможности

Провайдерский API рассчитан на:

- Вызовы с синтезом речи (text-to-speech)
- Отслеживание идентификатора вызова провайдера
- Колбэки статуса вызова
- Колбэки нажатия кнопок DTMF
- Действия ACK / Resolve с телефонной клавиатуры
- Опциональный опрос статуса вызова

## Структура каталогов

Каталог пользовательских провайдеров по умолчанию:

```text
/usr/local/lib/beacon/voice_providers
```

Пример:

```text
/usr/local/lib/beacon/voice_providers/
├── README.md
├── mango.py
├── zadarma.py
└── internal_pbx.py
```

Право на запись в этот каталог должно быть только у администраторов сервера, поскольку файлы провайдеров — это исполняемый Python-код.

Рекомендуемые права доступа:

```bash
sudo mkdir -p /usr/local/lib/beacon/voice_providers
sudo chown root:root /usr/local/lib/beacon/voice_providers
sudo chmod 755 /usr/local/lib/beacon/voice_providers
```

## Разделы документации

- [Провайдерский API](provider-api.md)
- [Настройка](configuration.md)
- [Колбэки и DTMF](callbacks.md)
- [Безопасность](security.md)
- [Устранение неполадок](troubleshooting.md)

## Примеры

Примеры файлов провайдеров хранятся в:

```text
examples/voice_providers/
```

Рекомендуемая точка старта:

```text
examples/voice_providers/example_http.py
```
