# Active scanning (Stage 6)

Цель: перевести "сырые" `scan_suggestions` (точки в мире) в понятные действия для оператора.

Философия
- Система обязана говорить "я не уверен" там, где много UNKNOWN либо reprojection не сходится.
- Планировщик лесов должен работать в консервативном режиме: UNKNOWN = blocked.

Поток
1. Android отправляет `POST /session/frame` (FramePacket) с RGB + pose + intrinsics (+ depth).
2. Backend:
   - интегрирует depth в `VoxelWorld` (FREE/OCCUPIED)
   - делает Stage 5 check (model vs depth) => `scan_suggestions`
   - делает Stage 6 plan => `scan_plan` (clusters + next_best_views)
3. Android показывает пользователю:
   - "куда навести камеру" (next_best_views)
   - индикатор готовности `readiness.ready_to_lock`

Endpoint
- `POST /session/scan_plan` - получить/обновить план без отправки нового кадра.

Readiness gates
Backend выставляет `ready_to_lock=false`, если:
- Stage 5 говорит `reprojection.ok=false`, или
- `unknown_local_ratio` рядом с камерой слишком высок, или
- `scan_suggestions` ещё много.

Дальше (Stage 6.2)
- Добавить "next best view" с вариацией углов (2-3 позы на cluster),
  плюс штраф за пути через UNKNOWN.
