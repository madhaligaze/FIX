# FIX Backend-AI

Цель: принять AR кадры (FramePacket), собрать геометрию рабочей зоны, вести policy/traces, и отдавать Android готовый bundle (окружение + леса + overlays).

Запуск

1) Установить зависимости (из Backend-AI):

pip install -r requirements.txt

2) Запустить:

uvicorn main:app --reload --host 127.0.0.1 --port 8000

Проверка

GET /health -> {"status":"ok"}
GET /policy/status -> текущий config + policy (и откуда загружено)

Артефакты

Все сохраняется в папку sessions/ (настраивается в config/default.yaml):
sessions/<session_id>/frames/... (входные кадры)
sessions/<session_id>/world/<rev>/... (env_mesh.obj, overlays, traces)
sessions/<session_id>/exports/<rev>/scene_bundle.json (handoff для Android)

Минимальный цикл API

1) Создать сессию:

POST /session/create

2) Отправить anchors (точки опоры/границы):

POST /session/anchors
{
  "session_id": "...",
  "anchors": [
    {"id":"s1","kind":"support","position":[0,0,0],"confidence":1.0},
    {"id":"s2","kind":"support","position":[4,4,0],"confidence":1.0}
  ]
}

3) Отправить кадр:

POST /session/frame (multipart/form-data)
  - meta: FramePacketMeta json
  - rgb: bytes
  - depth: uint16 raw bytes (если depth_meta задан)

4) Запросить scaffold bundle:

POST /session/<session_id>/request_scaffold
  - 200: вернет bundle и создаст export
  - 409 NEEDS_SCAN: вернет scan_plan + report
  - 409 UNSAFE: вернет violations + report

5) Забрать последний экспорт:

GET /session/<session_id>/export/latest

Конфиги

config/default.yaml - базовый runtime конфиг
policy/policy_config.yaml или Backend-AI/policy/policy_config.yaml - политика unknown/clearance/readiness/validators
