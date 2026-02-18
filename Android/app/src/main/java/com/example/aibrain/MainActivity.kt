package com.example.aibrain

import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.Looper
import android.util.Log
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.animation.AlphaAnimation
import android.view.animation.Animation
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Switch
import android.widget.ProgressBar
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.ar.core.Config
import com.google.ar.core.Plane
import com.google.ar.core.TrackingState
import com.google.ar.sceneform.AnchorNode
import com.google.ar.sceneform.Node
import com.google.ar.sceneform.math.Vector3
import com.google.ar.sceneform.rendering.Color as SceneColor
import com.example.aibrain.assets.ModelAssets
import com.example.aibrain.managers.ARSessionManager
import com.example.aibrain.scene.PhysicsAnimator
import com.example.aibrain.scene.SceneBuilder
import com.example.aibrain.scene.LightingSetup
import com.example.aibrain.scene.LayerGlbManager
import io.github.sceneview.ar.ArSceneView
import com.google.android.material.snackbar.Snackbar
import com.google.android.material.floatingactionbutton.FloatingActionButton
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import java.util.ArrayDeque
import java.util.concurrent.TimeUnit
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import kotlin.math.min
import com.example.aibrain.measurement.ARRuler
import com.example.aibrain.measurement.MeasurementType
import com.example.aibrain.measurement.Measurement
import com.example.aibrain.visualization.VoxelData
import com.example.aibrain.visualization.VoxelVisualizer

/**
 * ⚡⚡⚡ ФИНАЛЬНАЯ ВЕРСИЯ MainActivity ⚡⚡⚡
 *
 * ВКЛЮЧАЕТ:
 * ✅ Полный улучшенный Workflow (7 состояний)
 * ✅ Футуристичный UI (Cyan/Orange, без фиолетового)
 * ✅ AR Ruler интеграция (iOS Measure style)
 * ✅ 3D Model preview
 * ✅ Physics heatmap
 * ✅ Session management
 *
 * ВЕРСИЯ: 3.2 FINAL
 * ДАТА: 15.02.2026
 */
class MainActivity : AppCompatActivity() {

    // ══════════════════════════════════════════════════════════════════════
    // СОСТОЯНИЯ ПРИЛОЖЕНИЯ
    // ══════════════════════════════════════════════════════════════════════
    private enum class AppState {
        IDLE,           // Ожидание старта
        CONNECTING,     // Подключение к серверу
        SCANNING,       // Сканирование и установка точек
        MODELING,       // AI моделирует конструкцию
        PREVIEW_3D,     // Просмотр 3D модели
        SELECTING,      // Выбор варианта лесов
        RESULTS         // Финальные результаты
    }

    private enum class ConnectionStatus {
        UNKNOWN,
        ONLINE,
        RECONNECTING,
        OFFLINE
    }

    companion object {
        private const val MAX_SESSION_RETRY = 5
        private const val SESSION_RETRY_DELAY_MS = 1_500L
        private const val MAX_FAIL_WARN = 3
        private const val MAX_FAIL_RECONNECT = 6
        private const val RECONNECT_BASE_MS = 2_000L
        private const val RECONNECT_MAX_MS = 30_000L
        private const val STREAM_INTERVAL_MS = 1_000L
        private const val MIN_POINTS_FOR_MODEL = 2
        private const val MAX_POINTS = 20
        private const val PREFS_NAME = "app_settings"
        private const val PREF_SERVER_BASE_URL = "server_base_url"
    }

    // ══════════════════════════════════════════════════════════════════════
    // UI ЭЛЕМЕНТЫ - ОСНОВНЫЕ
    // ══════════════════════════════════════════════════════════════════════
    private lateinit var sceneView: ArSceneView
    private lateinit var arManager: ARSessionManager
    private lateinit var tvAiHint: TextView
    private lateinit var tvFrameCounter: TextView
    private lateinit var tvCoordX: TextView
    private lateinit var tvCoordY: TextView
    private lateinit var tvCoordZ: TextView
    private lateinit var tvPointsCount: TextView
    private lateinit var tvModeStatus: TextView
    private lateinit var statusIndicator: View
    private lateinit var tvSystemStatus: TextView
    private lateinit var pbQuality: ProgressBar
    private lateinit var tvQuality: TextView
    private lateinit var tvAiCritique: TextView

    // Основные кнопки
    private lateinit var btnStart: Button
    private lateinit var btnAddPoint: Button
    private lateinit var btnScan: Button
    private lateinit var btn3DModel: Button
    private lateinit var btnAnalyze: Button

    // Кнопки выбора вариантов
    private lateinit var btnVariant1: Button
    private lateinit var btnVariant2: Button
    private lateinit var btnVariant3: Button
    private lateinit var btnPhysics: Button
    private lateinit var btnAccept: Button

    // Дополнительные кнопки
    private lateinit var btnSaveSession: Button
    private lateinit var btnExport: Button
    private lateinit var btnSettings: Button
    private lateinit var btnRulerMode: Button
    private lateinit var fabEyeOfAI: FloatingActionButton
    private lateinit var voxelLegend: LinearLayout

    // Панели
    private lateinit var controlPanel: LinearLayout
    private lateinit var variantPanel: LinearLayout

    // ══════════════════════════════════════════════════════════════════════
    // UI ЭЛЕМЕНТЫ - AR RULER
    // ══════════════════════════════════════════════════════════════════════
    private lateinit var rulerOverlay: View
    private lateinit var tvDistanceValue: TextView
    private lateinit var tvRulerPointCount: TextView
    private lateinit var btnRulerMeasure: Button
    private lateinit var btnRulerUndo: Button
    private lateinit var btnRulerFinish: Button
    private lateinit var switchGrid: SwitchCompat
    private lateinit var switchSnap: SwitchCompat
    private lateinit var btnUnitsToggle: Button
    private lateinit var tvRulerInstruction: TextView
    private lateinit var accuracyDot: View
    private lateinit var tvAccuracy: TextView

    // ══════════════════════════════════════════════════════════════════════
    // СОСТОЯНИЕ - ОСНОВНОЕ
    // ══════════════════════════════════════════════════════════════════════
    private var appState = AppState.IDLE
    private var currentSessionId: String? = null
    private var isStreaming = false
    private var streamJob: Job? = null
    private var healthJob: Job? = null
    private var voxelPollJob: Job? = null
    private var connectionStatus: ConnectionStatus = ConnectionStatus.UNKNOWN
    private var lastConnectionDetail: String? = null
    private var consecutiveFailures = 0
    private var isReconnecting = false
    private var frameCount = 0
    private var lastQualityScore = 0.0
    private val hintHistory: ArrayDeque<String> = ArrayDeque()
    private val userMarkers = mutableListOf<Map<String, Float>>()
    private val anchorNodes = mutableListOf<AnchorNode>()
    private var lightingSetup = false
    private var mainAnchorNode: AnchorNode? = null

    // 3D Модель
    private var current3DModel: ModelingResponse? = null
    private var selectedVariantIndex = 0
    private var show3DPreview = false
    private val modelNodes = mutableListOf<Node>()
    private lateinit var sceneBuilder: SceneBuilder
    private lateinit var physicsAnimator: PhysicsAnimator
    private lateinit var viewModel: StructureViewModel
    private lateinit var soundManager: SoundManager
    private lateinit var modeIndicator: LinearLayout
    private lateinit var modeIcon: TextView
    private lateinit var modeText: TextView
    private lateinit var btnUndo: Button
    private lateinit var btnRedo: Button
    private var hasRedZones = false
    private lateinit var voxelVisualizer: VoxelVisualizer
    private var currentVoxelData: List<VoxelData>? = null
    private var eyeOfAIActive = false
    private var layerGlbManager: LayerGlbManager? = null
    private var exportedLayers: List<UiLayer> = emptyList()

    // ══════════════════════════════════════════════════════════════════════
    // СОСТОЯНИЕ - AR RULER
    // ══════════════════════════════════════════════════════════════════════
    private lateinit var arRuler: ARRuler
    private var rulerMode = false
    private var currentMeasurementType = MeasurementType.LINEAR

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var loadingDialog: AlertDialog? = null

    private lateinit var settingsPrefs: SharedPreferences
    private lateinit var api: ApiService

    // ══════════════════════════════════════════════════════════════════════
    // LIFECYCLE
    // ══════════════════════════════════════════════════════════════════════

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        settingsPrefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        rebuildApiClient()

        initViews()
        setupARScene()
        setupClickListeners()
        initializeRuler()
        sceneBuilder = SceneBuilder(sceneView.scene)
        physicsAnimator = PhysicsAnimator(sceneView, sceneBuilder, this)

        showLoadingDialog("Загрузка моделей...")
        lifecycleScope.launch {
            val result = ModelAssets.loadAll(this@MainActivity)
            result.onSuccess {
                hideLoadingDialog()
                Log.d("ModelAssets", "✅ Все модели загружены успешно")
            }
            result.onFailure { error ->
                hideLoadingDialog()
                Log.e("ModelAssets", "❌ Ошибка загрузки моделей: ${error.message}")
                showError("Не удалось загрузить 3D модели. Используется упрощенный режим.")
            }
        }
        viewModel = StructureViewModel(api)
        soundManager = SoundManager(this)
        voxelVisualizer = VoxelVisualizer(sceneView.scene, sceneView, lifecycleScope)

        lifecycleScope.launch {
            viewModel.structureState.collect { state ->
                handleStructureState(state)
            }
        }


        lifecycleScope.launch {
            viewModel.editMode.collect { mode ->
                updateModeUI(mode)
            }
        }

        btnUndo.setOnClickListener { performUndo() }
        btnRedo.setOnClickListener { performRedo() }

        scope.launch {
            while (isActive) {
                updateUndoRedoButtons()
                delay(100)
            }
        }

        viewModel.saveSnapshot(sceneBuilder.getAllElements(), "Исходное состояние")

        startHealthLoop()
        updateConnectionUi(ConnectionStatus.UNKNOWN, "")

        transitionTo(AppState.IDLE)
    }

    private fun initViews() {
        // Основные элементы
        sceneView = findViewById(R.id.sceneView)
        tvAiHint = findViewById(R.id.tv_ai_hint)
        tvFrameCounter = findViewById(R.id.tv_frame_counter)
        tvCoordX = findViewById(R.id.tv_coord_x)
        tvCoordY = findViewById(R.id.tv_coord_y)
        tvCoordZ = findViewById(R.id.tv_coord_z)
        tvPointsCount = findViewById(R.id.tv_points_count)
        tvModeStatus = findViewById(R.id.tv_mode_status)
        statusIndicator = findViewById(R.id.status_indicator)
        tvSystemStatus = findViewById(R.id.tv_system_status)
        pbQuality = findViewById(R.id.pb_quality)
        tvQuality = findViewById(R.id.tv_quality)
        tvAiCritique = findViewById(R.id.tv_ai_critique)

        // Основные кнопки
        btnStart = findViewById(R.id.btn_start)
        btnAddPoint = findViewById(R.id.btn_add_point)
        btnScan = findViewById(R.id.btn_scan)
        btn3DModel = findViewById(R.id.btn_3d_model)
        btnAnalyze = findViewById(R.id.btn_analyze)

        // Кнопки вариантов
        btnVariant1 = findViewById(R.id.btn_variant_1)
        btnVariant2 = findViewById(R.id.btn_variant_2)
        btnVariant3 = findViewById(R.id.btn_variant_3)
        btnPhysics = findViewById(R.id.btn_physics)
        btnAccept = findViewById(R.id.btn_accept)

        // Дополнительные
        btnSaveSession = findViewById(R.id.btn_save_session)
        btnExport = findViewById(R.id.btn_export)
        btnSettings = findViewById(R.id.btn_settings)
        btnRulerMode = findViewById(R.id.btn_ruler_mode)
        fabEyeOfAI = findViewById(R.id.fab_eye_of_ai)
        voxelLegend = findViewById(R.id.voxel_legend)

        // Панели
        controlPanel = findViewById(R.id.control_panel)
        variantPanel = findViewById(R.id.variant_panel)
        modeIndicator = findViewById(R.id.mode_indicator)
        modeIcon = findViewById(R.id.mode_icon)
        modeText = findViewById(R.id.mode_text)
        btnUndo = findViewById(R.id.btn_undo)
        btnRedo = findViewById(R.id.btn_redo)

        // AR Ruler элементы
        rulerOverlay = findViewById(R.id.ruler_overlay)
        tvDistanceValue = findViewById(R.id.tv_distance_value)
        tvRulerPointCount = findViewById(R.id.tv_point_count)
        btnRulerMeasure = findViewById(R.id.btn_ruler_measure)
        btnRulerUndo = findViewById(R.id.btn_ruler_undo)
        btnRulerFinish = findViewById(R.id.btn_ruler_finish)
        switchGrid = findViewById(R.id.switch_grid)
        switchSnap = findViewById(R.id.switch_snap)
        btnUnitsToggle = findViewById(R.id.btn_units_toggle)
        tvRulerInstruction = findViewById(R.id.tv_ruler_instruction)
        accuracyDot = findViewById(R.id.accuracy_dot)
        tvAccuracy = findViewById(R.id.tv_accuracy)
    }

    private fun setupARScene() {
        sceneView.configureSession { _, config ->
            config.focusMode = Config.FocusMode.AUTO
            config.lightEstimationMode = Config.LightEstimationMode.ENVIRONMENTAL_HDR
            config.planeFindingMode = Config.PlaneFindingMode.HORIZONTAL_AND_VERTICAL
        }


        if (!::arManager.isInitialized) {
            arManager = ARSessionManager(this, sceneView)
            arManager.setupSession()
        }

        sceneView.renderer?.apply {
            isShadowsEnabled = true
            isScreenSpaceAmbientOcclusionEnabled = true
            isBloomEnabled = true
            isMultisampleAntiAliasingEnabled = true
        }

        if (mainAnchorNode == null) {
            mainAnchorNode = AnchorNode().also { anchor ->
                anchor.setParent(sceneView.scene)
                anchorNodes.add(anchor)
            }
        }

        sceneView.scene.addOnUpdateListener {
            val anchor = mainAnchorNode
            if (anchor != null && !lightingSetup) {
                LightingSetup.setupLighting(sceneView, anchor)
                lightingSetup = true
            }
        }

        // Обновление координат камеры в реальном времени
        scope.launch {
            while (isActive) {
                updateCameraCoordinates()
                delay(100)
            }
        }
    }

    private fun setupClickListeners() {
        // Основные действия
        btnStart.setOnClickListener { onStartClicked() }
        btnAddPoint.setOnClickListener { onAddPointClicked() }
        btnScan.setOnClickListener { onScanClicked() }
        btn3DModel.setOnClickListener { on3DModelClicked() }
        btnAnalyze.setOnClickListener { onAnalyzeClicked() }
        tvAiHint.setOnClickListener { showHintHistoryDialog() }

        // Выбор вариантов
        btnVariant1.setOnClickListener { onVariantSelected(0) }
        btnVariant2.setOnClickListener { onVariantSelected(1) }
        btnVariant3.setOnClickListener { onVariantSelected(2) }
        btnPhysics.setOnClickListener { onPhysicsClicked() }
        btnAccept.setOnClickListener { onAcceptClicked() }

        // Дополнительные
        btnSaveSession.setOnClickListener { onSaveSessionClicked() }
        btnExport.setOnClickListener { onExportClicked() }
        btnSettings.setOnClickListener { onSettingsClicked() }
        fabEyeOfAI.setOnClickListener { toggleEyeOfAI() }
        btnRulerMode.setOnClickListener { toggleRulerMode() }

        // AR Ruler
        btnRulerMeasure.setOnClickListener { onRulerMeasureClick() }
        btnRulerUndo.setOnClickListener { onRulerUndoClick() }
        btnRulerFinish.setOnClickListener { onRulerFinishClick() }
        btnUnitsToggle.setOnClickListener { toggleUnits() }

        // Ruler mode buttons
        findViewById<Button>(R.id.btn_mode_linear).setOnClickListener {
            setMeasurementMode(MeasurementType.LINEAR)
        }
        findViewById<Button>(R.id.btn_mode_height).setOnClickListener {
            setMeasurementMode(MeasurementType.HEIGHT)
        }
        findViewById<Button>(R.id.btn_mode_area).setOnClickListener {
            setMeasurementMode(MeasurementType.AREA)
        }
    }

    private fun initializeRuler() {
        // Создание ARRuler instance
        arRuler = ARRuler(sceneView, scope)

        // Callbacks
        arRuler.onMeasurementUpdate = { distance, label ->
            updateRulerDisplay(distance, label)
        }

        arRuler.onMeasurementComplete = { measurement ->
            onMeasurementSaved(measurement)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        stopStreaming()
        stopHealthLoop()
        scope.cancel()
        clearARAnchors()

        if (::arRuler.isInitialized) {
            arRuler.clearAll()
        }
        if (::physicsAnimator.isInitialized) {
            physicsAnimator.release()
        }
        if (::soundManager.isInitialized) {
            soundManager.release()
        }
        if (::voxelVisualizer.isInitialized) {
            voxelVisualizer.hideVoxels()
        }

        hideLoadingDialog()
        ModelAssets.clear()
    }

    // ══════════════════════════════════════════════════════════════════════
    // ОСНОВНОЙ WORKFLOW - ОБРАБОТКА КНОПОК
    // ══════════════════════════════════════════════════════════════════════

    private fun onStartClicked() {
        if (appState != AppState.IDLE) return

        showHint("⚡ Инициализация системы...")
        transitionTo(AppState.CONNECTING)

        scope.launch { doStartSession() }
    }

    private fun onAddPointClicked() {
        if (appState != AppState.SCANNING) return

        if (userMarkers.size >= MAX_POINTS) {
            showHint("⚠️ Достигнут максимум точек: $MAX_POINTS")
            return
        }

        placeAnchor()
    }

    private fun onScanClicked() {
        if (appState != AppState.SCANNING) return

        showHint("📡 Интенсивное сканирование...")

        scope.launch {
            repeat(5) {
                if (!isStreaming) return@launch
                sendFrame()
                delay(300)
            }
            showHint("✓ Сканирование завершено. Качество: ${lastQualityScore.toInt()}%")
        }
    }

    private fun on3DModelClicked() {
        if (appState != AppState.SCANNING && appState != AppState.PREVIEW_3D) return

        if (appState == AppState.PREVIEW_3D) {
            hide3DPreview()
            transitionTo(AppState.SCANNING)
        } else {
            show3DPreview = true
            showHint("🌐 Отображение текущей 3D модели...")
            request3DReconstruction()
        }
    }

    private fun onAnalyzeClicked() {
        if (appState != AppState.SCANNING) return

        if (userMarkers.size < MIN_POINTS_FOR_MODEL) {
            showHint("📍 Требуется минимум $MIN_POINTS_FOR_MODEL точки. Сейчас: ${userMarkers.size}")
            vibrate()
            return
        }

        showHint("🧠 Запуск анализа структуры...")
        stopStreaming()
        transitionTo(AppState.MODELING)

        scope.launch { doRequestModeling() }
    }

    private fun onVariantSelected(index: Int) {
        if (appState != AppState.SELECTING) return

        selectedVariantIndex = index

        listOf(btnVariant1, btnVariant2, btnVariant3).forEachIndexed { i, btn ->
            if (i == index) {
                btn.setBackgroundColor(ContextCompat.getColor(this, R.color.cyan_primary))
                btn.setTextColor(Color.BLACK)
            } else {
                btn.setBackgroundColor(ContextCompat.getColor(this, R.color.transparent_panel))
                btn.setTextColor(ContextCompat.getColor(this, R.color.cyan_primary))
            }
        }

        visualizeScaffoldVariant(selectedVariantIndex)

        val option = current3DModel?.options?.get(index)
        if (option != null) {
            showHint("✓ Вариант ${index + 1}: ${option.variant_name} | Надёжность: ${option.safety_score}%")
            val critique = option.ai_critique?.joinToString("\n")?.trim().orEmpty()
            if (critique.isNotBlank()) {
                tvAiCritique.visibility = View.VISIBLE
                tvAiCritique.text = critique
            } else {
                tvAiCritique.visibility = View.GONE
            }

            scope.launch {
                sendLogEvent(
                    "VARIANT_SELECTED",
                    mapOf("variant_index" to index, "variant_name" to option.variant_name, "safety_score" to option.safety_score)
                )
            }
        }
    }

    private fun onPhysicsClicked() {
        if (appState != AppState.SELECTING) return
        showHint("📊 Отображение карты нагрузок...")
        showPhysicsHeatmap()
    }

    private fun onAcceptClicked() {
        if (appState != AppState.SELECTING) return

        val option = current3DModel?.options?.get(selectedVariantIndex)
        if (option == null) {
            showHint("⚠️ Не выбран вариант")
            return
        }

        showHint("✅ Вариант «${option.variant_name}» утвержден!")
        transitionTo(AppState.RESULTS)

        scope.launch {
            sendLogEvent(
                "VARIANT_ACCEPTED",
                mapOf("variant_index" to selectedVariantIndex, "variant_name" to option.variant_name)
            )
            delay(600)
            currentSessionId?.let { sid ->
                runCatching {
                    val resp = api.exportLatest(sid)
                    if (resp.isSuccessful && resp.body() != null) {
                        val rev = resp.body()!!.revision_id ?: resp.body()!!.rev_id.orEmpty()
                        if (rev.isNotBlank()) showHint("✓ Экспорт сформирован: ${rev.take(8)}")
                    }
                }
            }
            delay(2000)
            showFinalResults(option)
        }
    }

    private fun onSaveSessionClicked() {
        val sid = currentSessionId
        if (sid.isNullOrBlank()) {
            showHint("⚠️ Нет активной сессии")
            return
        }

        showHint("💾 Формирование export/latest...")
        scope.launch {
            try {
                val resp = api.exportLatest(sid)
                if (!resp.isSuccessful || resp.body() == null) {
                    showError("export/latest: HTTP ${resp.code()}")
                    return@launch
                }

                val rev = resp.body()!!.revision_id ?: resp.body()!!.rev_id.orEmpty()
                sendLogEvent("SESSION_SAVED", mapOf("revision_id" to rev))
                showHint("✓ Сессия сохранена: ${rev.take(8)}")
            } catch (e: Exception) {
                showError("Ошибка сохранения: ${e.message}")
            }
        }
    }

    private fun onExportClicked() {
        val sid = currentSessionId
        if (sid.isNullOrBlank()) {
            showHint("⚠️ Нет активной сессии")
            return
        }

        showHint("📦 Загрузка export/latest...")
        scope.launch {
            try {
                val response = api.exportLatest(sid)
                if (!response.isSuccessful || response.body() == null) {
                    throw IllegalStateException("HTTP ${response.code()}")
                }
                val bundle = response.body()!!
                val layers = bundle.ui?.layers.orEmpty()
                exportedLayers = layers
                if (layerGlbManager == null) {
                    layerGlbManager = LayerGlbManager(this@MainActivity, sceneView.scene, getCurrentServerUrl())
                }

                for (layer in layers) {
                    val path = layer.file?.glb?.path ?: layer.file?.path
                    if (path.isNullOrBlank()) continue
                    runCatching { layerGlbManager?.loadLayer(layer.id, path) }
                }

                showLayersDialog()
                showHint("✓ Слои загружены")
            } catch (e: Exception) {
                showHint("❌ Ошибка загрузки слоёв: ${e.message}")
            }
        }
    }

    private fun showLayersDialog() {
        if (exportedLayers.isEmpty()) {
            showHint("⚠️ Нет доступных слоёв")
            return
        }

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 24, 48, 8)
        }

        exportedLayers.forEach { layer ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                val p = (resources.displayMetrics.density * 8).toInt()
                setPadding(0, p, 0, p)
            }
            val label = TextView(this).apply {
                text = layer.label ?: layer.id
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }
            val sw = Switch(this).apply {
                val key = "layer_visible_${layer.id}"
                val def = layer.default_on ?: true
                isChecked = settingsPrefs.getBoolean(key, def)
                setOnCheckedChangeListener { _, checked ->
                    settingsPrefs.edit().putBoolean(key, checked).apply()
                    layerGlbManager?.setVisible(layer.id, checked)
                }
            }
            row.addView(label)
            row.addView(sw)
            container.addView(row)
            layerGlbManager?.setVisible(layer.id, sw.isChecked)
        }

        AlertDialog.Builder(this)
            .setTitle("Layers")
            .setView(container)
            .setPositiveButton("OK", null)
            .show()
    }

    private fun onSettingsClicked() {
        val currentBaseUrl = getCurrentServerUrl()
        val input = EditText(this).apply {
            hint = "http://192.168.1.10:8000/"
            setSingleLine()
            setText(currentBaseUrl)
            setSelection(text.length)
        }

        AlertDialog.Builder(this)
            .setTitle("⚙️ Настройки сервера")
            .setMessage("Укажите IP/URL backend сервера. Пример: http://192.168.1.10:8000/")
            .setView(input)
            .setPositiveButton("Сохранить") { _, _ ->
                val normalizedUrl = normalizeBaseUrl(input.text.toString())
                if (normalizedUrl == null) {
                    showError("Неверный URL сервера")
                    return@setPositiveButton
                }

                settingsPrefs.edit().putString(PREF_SERVER_BASE_URL, normalizedUrl).apply()
                rebuildApiClient()
                showHint("✓ Сервер обновлен: $normalizedUrl")
            }
            .setNeutralButton("По умолчанию") { _, _ ->
                settingsPrefs.edit().remove(PREF_SERVER_BASE_URL).apply()
                rebuildApiClient()
                showHint("✓ Восстановлен сервер по умолчанию: ${getCurrentServerUrl()}")
            }
            .setNegativeButton("Отмена", null)
            .show()
    }

    private fun rebuildApiClient() {
        val baseUrl = getCurrentServerUrl()

        val logging = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BASIC else HttpLoggingInterceptor.Level.NONE
        }

        val client = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(25, TimeUnit.SECONDS)
            .writeTimeout(25, TimeUnit.SECONDS)
            .addInterceptor(logging)
            .build()

        api = retrofit2.Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(retrofit2.converter.gson.GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)

        if (::viewModel.isInitialized) {
            viewModel.updateApiService(api)
        }
        if (::statusIndicator.isInitialized && ::tvSystemStatus.isInitialized) {
            updateConnectionUi(ConnectionStatus.UNKNOWN, "${baseUrl}")
        }
    }

    private fun getCurrentServerUrl(): String {
        val saved = settingsPrefs.getString(PREF_SERVER_BASE_URL, null)
        return normalizeBaseUrl(saved) ?: BuildConfig.BACKEND_BASE_URL
    }

    private fun normalizeBaseUrl(raw: String?): String? {
        val value = raw?.trim().orEmpty()
        if (value.isBlank()) return null

        val withScheme = if (value.startsWith("http://") || value.startsWith("https://")) {
            value
        } else {
            "http://$value"
        }

        val withTrailingSlash = if (withScheme.endsWith('/')) withScheme else "$withScheme/"
        return withTrailingSlash.toHttpUrlOrNull()?.toString()
    }


    // ══════════════════════════════════════════════════════════════════════
    // СЕТЬ / СТАТУС СЕРВЕРА
    // ══════════════════════════════════════════════════════════════════════

    private fun updateConnectionUi(status: ConnectionStatus, detail: String? = null) {
        connectionStatus = status
        lastConnectionDetail = detail

        val (dotRes, label) = when (status) {
            ConnectionStatus.ONLINE -> R.drawable.ic_status_dot_green to "SYSTEM ONLINE"
            ConnectionStatus.RECONNECTING -> R.drawable.ic_status_dot_orange to "RECONNECTING..."
            ConnectionStatus.OFFLINE -> R.drawable.ic_status_dot_red to "SYSTEM OFFLINE"
            ConnectionStatus.UNKNOWN -> R.drawable.ic_status_dot_cyan to "SYSTEM"
        }

        statusIndicator.setBackgroundResource(dotRes)
        tvSystemStatus.text = if (detail.isNullOrBlank()) label else (label + " | " + detail)
    }

    private fun startHealthLoop() {
        healthJob?.cancel()
        healthJob = scope.launch(Dispatchers.IO) {
            while (isActive) {
                val ok = try {
                    val r = api.healthCheck()
                    r.isSuccessful
                } catch (_: Exception) {
                    false
                }

                withContext(Dispatchers.Main) {
                    val base = getCurrentServerUrl().trimEnd('/')
                    if (ok) {
                        updateConnectionUi(ConnectionStatus.ONLINE, base)
                    } else {
                        // Если сейчас идет стрим - показываем деградацию, иначе OFFLINE
                        val st = if (isStreaming) ConnectionStatus.RECONNECTING else ConnectionStatus.OFFLINE
                        updateConnectionUi(st, base)
                    }
                }

                delay(3_000L)
            }
        }
    }

    private fun stopHealthLoop() {
        healthJob?.cancel()
        healthJob = null
    }

    private suspend fun syncAnchorsToServer() {
        val sid = currentSessionId ?: return
        val anchors = userMarkers.mapIndexed { index, m ->
            val x = m["x"] ?: 0f
            val y = m["y"] ?: 0f
            val z = m["z"] ?: 0f
            AnchorPointRequest(
                id = "a" + (index + 1),
                kind = "support",
                position = listOf(x, y, z),
                confidence = 1.0f
            )
        }
        if (anchors.isEmpty()) return

        val resp = api.postAnchors(AnchorPayload(session_id = sid, anchors = anchors))
        if (!resp.isSuccessful) {
            throw IllegalStateException("/session/anchors HTTP " + resp.code())
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    // AR RULER - ОБРАБОТКА КНОПОК
    // ══════════════════════════════════════════════════════════════════════

    private fun toggleRulerMode() {
        rulerMode = !rulerMode

        if (rulerMode) {
            // Включение режима рулетки
            rulerOverlay.visibility = View.VISIBLE
            controlPanel.visibility = View.GONE

            arRuler.startMeasurement(currentMeasurementType)

            showHint("📏 Режим измерения активен")
            updateModeStatus("ИЗМЕРЕНИЕ")
        } else {
            // Выключение режима рулетки
            rulerOverlay.visibility = View.GONE
            controlPanel.visibility = View.VISIBLE

            showHint("📡 Режим сканирования")
            updateModeStatus("СКАНИРОВАНИЕ")
        }
    }

    private fun onRulerMeasureClick() {
        if (!rulerMode) return

        try {
            val frame = sceneView.arSession?.update() ?: return

            val hits = frame.hitTest(
                sceneView.width / 2f,
                sceneView.height / 2f
            )

            val hit = hits.firstOrNull { it.trackable is Plane } ?: return

            val success = arRuler.addMeasurementPoint(hit)

            if (success) {
                vibrate(30)

                val pointCount = arRuler.getCurrentDistance()
                tvRulerPointCount.text = "$pointCount"

                if (pointCount >= 2) {
                    btnRulerFinish.visibility = View.VISIBLE
                    btnRulerMeasure.text = "+ ЕЩЁ"
                }
            } else {
                Toast.makeText(this, "❌ Не удалось установить точку", Toast.LENGTH_SHORT).show()
                vibrate(100)
            }

        } catch (e: Exception) {
            showHint("⚠️ Ошибка: ${e.message}")
        }
    }

    private fun onRulerUndoClick() {
        arRuler.undoLastPoint()

        val distance = arRuler.getCurrentDistance()
        updateRulerDisplay(distance, formatDistance(distance))
    }

    private fun onRulerFinishClick() {
        val measurement = arRuler.finishMeasurement()

        if (measurement != null) {
            showHint("✅ Измерение сохранено: ${measurement.label}")

            tvDistanceValue.text = "0.00 m"
            tvRulerPointCount.text = "0"
            btnRulerFinish.visibility = View.GONE
            btnRulerMeasure.text = "+ ТОЧКА"

            vibrate(50)
        }
    }

    private fun setMeasurementMode(type: MeasurementType) {
        currentMeasurementType = type

        val btnLinear = findViewById<Button>(R.id.btn_mode_linear)
        val btnHeight = findViewById<Button>(R.id.btn_mode_height)
        val btnArea = findViewById<Button>(R.id.btn_mode_area)

        listOf(btnLinear, btnHeight, btnArea).forEach {
            it.setBackgroundResource(R.drawable.btn_mode_inactive)
            it.setTextColor(ContextCompat.getColor(this, R.color.cyan_alpha_40))
        }

        val activeBtn = when (type) {
            MeasurementType.LINEAR -> btnLinear
            MeasurementType.HEIGHT -> btnHeight
            MeasurementType.AREA -> btnArea
            else -> btnLinear
        }

        activeBtn.setBackgroundResource(R.drawable.btn_mode_active)
        activeBtn.setTextColor(ContextCompat.getColor(this, R.color.cyan_primary))

        arRuler.startMeasurement(type)

        val instruction = when (type) {
            MeasurementType.LINEAR -> "Нажмите на 2 точки для измерения расстояния"
            MeasurementType.HEIGHT -> "Нажмите на точку для измерения высоты от пола"
            MeasurementType.AREA -> "Нажмите точки по периметру для измерения площади"
            else -> "Выберите режим измерения"
        }

        tvRulerInstruction.text = instruction
    }

    private fun toggleUnits() {
        arRuler.units = if (arRuler.units == ARRuler.Units.METRIC) {
            ARRuler.Units.IMPERIAL
        } else {
            ARRuler.Units.METRIC
        }

        btnUnitsToggle.text = if (arRuler.units == ARRuler.Units.METRIC) "м" else "ft"

        val distance = arRuler.getCurrentDistance()
        updateRulerDisplay(distance, formatDistance(distance))
    }

    private fun updateRulerDisplay(distance: Float, label: String) {
        tvDistanceValue.text = label

        val accuracy = getTrackingAccuracy()
        updateAccuracyIndicator(accuracy)
    }

    private fun onMeasurementSaved(measurement: Measurement) {
        Toast.makeText(this, "💾 Измерение: ${measurement.label}", Toast.LENGTH_SHORT).show()
    }

    private fun getTrackingAccuracy(): Float {
        try {
            val frame = sceneView.arSession?.update() ?: return 0.5f
            val camera = frame.camera

            return when (camera.trackingState) {
                TrackingState.TRACKING -> 0.95f
                TrackingState.PAUSED -> 0.6f
                else -> 0.3f
            }
        } catch (e: Exception) {
            return 0.5f
        }
    }

    private fun updateAccuracyIndicator(accuracy: Float) {
        when {
            accuracy >= 0.9f -> {
                accuracyDot.setBackgroundResource(R.drawable.ic_dot_green)
                tvAccuracy.text = "Точность: высокая"
                tvAccuracy.setTextColor(ContextCompat.getColor(this, R.color.green_primary))
            }
            accuracy >= 0.6f -> {
                accuracyDot.setBackgroundResource(R.drawable.ic_dot_orange)
                tvAccuracy.text = "Точность: средняя"
                tvAccuracy.setTextColor(ContextCompat.getColor(this, R.color.orange_primary))
            }
            else -> {
                accuracyDot.setBackgroundResource(R.drawable.ic_dot_red)
                tvAccuracy.text = "Точность: низкая"
                tvAccuracy.setTextColor(ContextCompat.getColor(this, R.color.red_primary))
            }
        }
    }

    private fun formatDistance(meters: Float): String {
        return when (arRuler.units) {
            ARRuler.Units.METRIC -> {
                when {
                    meters < 0.01f -> "${(meters * 1000).toInt()} мм"
                    meters < 1.0f -> "${(meters * 100).toInt()} см"
                    meters < 10.0f -> String.format("%.2f м", meters)
                    else -> String.format("%.1f м", meters)
                }
            }
            ARRuler.Units.IMPERIAL -> {
                val feet = meters * 3.28084f
                val inches = (feet % 1) * 12
                "${feet.toInt()}' ${inches.toInt()}\""
            }
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    // УПРАВЛЕНИЕ СОСТОЯНИЕМ
    // ══════════════════════════════════════════════════════════════════════

    private fun transitionTo(state: AppState) {
        appState = state

        when (state) {
            AppState.IDLE -> {
                showControls(btnStart)
                hideControls(btnAddPoint, btnScan, btn3DModel, btnAnalyze)
                variantPanel.visibility = View.GONE
                btnRulerMode.visibility = View.GONE

                showHint("👁️ Наведите камеру на конструкцию")
                updateModeStatus("ОЖИДАНИЕ")
                stopBlinkAnimation(tvAiHint)
            }

            AppState.CONNECTING -> {
                hideAllControls()
                showHint("⏳ Подключение к AI Brain...")
                updateModeStatus("ПОДКЛЮЧЕНИЕ")
                startBlinkAnimation(tvAiHint)
            }

            AppState.SCANNING -> {
                hideControls(btnStart)
                showControls(btnAddPoint, btnScan, btn3DModel, btnAnalyze)
                btnRulerMode.visibility = View.VISIBLE
                variantPanel.visibility = View.GONE

                btnAnalyze.isEnabled = userMarkers.size >= MIN_POINTS_FOR_MODEL

                showHint("📡 Система активна | Точек: ${userMarkers.size}")
                updateModeStatus("СКАНИРОВАНИЕ")
                stopBlinkAnimation(tvAiHint)
            }

            AppState.MODELING -> {
                hideAllControls()
                showHint("🧠 AI анализирует структуру...")
                updateModeStatus("МОДЕЛИРОВАНИЕ")
                startBlinkAnimation(tvAiHint)
            }

            AppState.PREVIEW_3D -> {
                showControls(btnAddPoint, btnAnalyze)
                hideControls(btnStart, btnScan)
                variantPanel.visibility = View.GONE

                showHint("🌐 3D модель отображена")
                updateModeStatus("ПРЕВЬЮ")
            }

            AppState.SELECTING -> {
                hideAllControls()
                variantPanel.visibility = View.VISIBLE

                showHint("🎯 Выберите вариант лесов")
                updateModeStatus("ВЫБОР ВАРИАНТА")
                stopBlinkAnimation(tvAiHint)
            }

            AppState.RESULTS -> {
                showControls(btnStart)
                btnStart.text = "ЗАНОВО"
                hideControls(btnAddPoint, btnScan, btn3DModel, btnAnalyze)
                variantPanel.visibility = View.GONE

                updateModeStatus("ЗАВЕРШЕНО")
                stopBlinkAnimation(tvAiHint)
            }
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    // ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ (остальной код аналогично предыдущей версии)
    // ══════════════════════════════════════════════════════════════════════

    private fun showControls(vararg buttons: Button) {
        buttons.forEach { it.visibility = View.VISIBLE }
    }

    private fun hideControls(vararg buttons: Button) {
        buttons.forEach { it.visibility = View.GONE }
    }

    private fun hideAllControls() {
        hideControls(btnStart, btnAddPoint, btnScan, btn3DModel, btnAnalyze)
        btnRulerMode.visibility = View.GONE
    }

    private fun updateModeStatus(status: String) {
        tvModeStatus.text = "РЕЖИМ: $status"
    }

    private fun updateQualityUI(score: Double?) {
        val v = score ?: return
        lastQualityScore = v
        val clamped = v.coerceIn(0.0, 100.0)
        pbQuality.progress = clamped.toInt()
        tvQuality.text = "${clamped.toInt()}%"
    }

    private fun showHintHistoryDialog() {
        if (hintHistory.isEmpty()) return
        val items = hintHistory.toList().reversed().take(12)
        AlertDialog.Builder(this)
            .setTitle("AI Log")
            .setItems(items.toTypedArray(), null)
            .setPositiveButton("OK", null)
            .show()
    }

    private fun showHint(text: String) {
        tvAiHint.text = text
        hintHistory.addLast(text)
        while (hintHistory.size > 10) hintHistory.removeFirst()
    }

    private fun updateFrameCounter() {
        tvFrameCounter.text = "FRM:${frameCount.toString().padStart(4, '0')}"
    }

    private fun updatePointsCount() {
        tvPointsCount.text = "PTS:${userMarkers.size}"
    }

    private fun updateCameraCoordinates() {
        try {
            val frame = sceneView.arSession?.update() ?: return
            val pose = frame.camera.displayOrientedPose

            tvCoordX.text = "X:${"%.2f".format(pose.tx())}"
            tvCoordY.text = "Y:${"%.2f".format(pose.ty())}"
            tvCoordZ.text = "Z:${"%.2f".format(pose.tz())}"
        } catch (e: Exception) {
            // Ignore
        }
    }

    private fun startBlinkAnimation(view: View) {
        val anim = AlphaAnimation(1.0f, 0.3f).apply {
            duration = 700
            repeatCount = Animation.INFINITE
            repeatMode = Animation.REVERSE
        }
        view.startAnimation(anim)
    }

    private fun stopBlinkAnimation(view: View) {
        view.clearAnimation()
        view.alpha = 1.0f
    }

    private fun vibrate(durationMs: Long = 50) {
        try {
            val vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator.vibrate(VibrationEffect.createOneShot(durationMs, VibrationEffect.DEFAULT_AMPLITUDE))
            } else {
                @Suppress("DEPRECATION")
                vibrator.vibrate(durationMs)
            }
        } catch (_: Exception) {
            // Ignore
        }
    }

    private suspend fun doStartSession() {
        val base = getCurrentServerUrl().trimEnd('/')
        updateConnectionUi(ConnectionStatus.UNKNOWN, base)

        var lastError: String? = null
        for (attempt in 1..MAX_SESSION_RETRY) {
            try {
                // Быстрый health-check до создания сессии
                val healthOk = try {
                    api.healthCheck().isSuccessful
                } catch (_: Exception) {
                    false
                }

                if (!healthOk) {
                    updateConnectionUi(ConnectionStatus.OFFLINE, base)
                    lastError = "HEALTH_FAIL"
                    delay(SESSION_RETRY_DELAY_MS * attempt)
                    continue
                }

                val response = api.startSession()
                if (response.isSuccessful && response.body() != null) {
                    val sessionId = response.body()!!.session_id
                    currentSessionId = sessionId
                    viewModel.setSessionId(sessionId)

                    consecutiveFailures = 0
                    frameCount = 0

                    updateConnectionUi(ConnectionStatus.ONLINE, base)
                    showHint("✓ Сессия создана")
                    transitionTo(AppState.SCANNING)
                    startStreamingLoop()
                    return
                } else {
                    lastError = "HTTP " + response.code()
                }
            } catch (e: Exception) {
                lastError = e.message
            }

            updateConnectionUi(ConnectionStatus.RECONNECTING, base)
            delay(SESSION_RETRY_DELAY_MS * attempt)
        }

        showError("Не удалось создать сессию: " + (lastError ?: "UNKNOWN"))
        transitionTo(AppState.IDLE)
    }

    private fun startStreamingLoop() {
        if (isStreaming) return
        val sid = currentSessionId ?: return

        isStreaming = true
        streamJob?.cancel()
        streamJob = scope.launch {
            while (isActive && isStreaming && currentSessionId == sid) {
                val ok = try {
                    withContext(Dispatchers.IO) { sendFrame() }
                } catch (_: Exception) {
                    false
                }

                if (!ok) {
                    consecutiveFailures += 1
                } else {
                    consecutiveFailures = 0
                }

                if (consecutiveFailures >= MAX_FAIL_RECONNECT) {
                    val base = getCurrentServerUrl().trimEnd('/')
                    updateConnectionUi(ConnectionStatus.OFFLINE, base)
                    val backoff = min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * consecutiveFailures.toLong())
                    delay(backoff)
                } else if (consecutiveFailures > 0) {
                    val base = getCurrentServerUrl().trimEnd('/')
                    updateConnectionUi(ConnectionStatus.RECONNECTING, base)
                }

                updateFrameCounter()
                updateCameraCoordinates()
                delay(STREAM_INTERVAL_MS)
            }
        }
    }

    private suspend fun sendFrame(): Boolean {
        val sid = currentSessionId ?: return false

        // 1) Сбор данных кадра с main thread
        val payload = withContext(Dispatchers.Main) {
            val frame = try {
                sceneView.arSession?.update()
            } catch (_: Exception) {
                null
            } ?: return@withContext null

            try {
                val cam = frame.camera
                if (cam.trackingState != TrackingState.TRACKING) return@withContext null

                // RGB
                val image = try {
                    frame.acquireCameraImage()
                } catch (_: Exception) {
                    null
                } ?: return@withContext null

                val rgbBase64 = try {
                    ImageUtils.imageToBase64(image)
                } finally {
                    try { image.close() } catch (_: Exception) { }
                }

                // Intrinsics
                val intr = cam.imageIntrinsics
                val focal = intr.focalLength
                val pp = intr.principalPoint
                val dims = intr.imageDimensions

                val fx = focal[0].toDouble()
                val fy = focal[1].toDouble()
                val cx = pp[0].toDouble()
                val cy = pp[1].toDouble()
                val w = dims[0].toInt()
                val h = dims[1].toInt()

                // Pose
                val pose = cam.pose
                val q = FloatArray(4)
                pose.getRotationQuaternion(q, 0)
                val position = listOf(pose.tx(), pose.ty(), pose.tz())
                val quaternion = listOf(q[0], q[1], q[2], q[3])

                // Point cloud
                val pc = try {
                    frame.acquirePointCloud()
                } catch (_: Exception) {
                    null
                }

                val points: List<List<Float>> = if (pc != null) {
                    try {
                        val buf = pc.points
                        val total = buf.remaining() / 4
                        val cap = 3000
                        val step = maxOf(1, total / cap)
                        val out = ArrayList<List<Float>>(min(total, cap))
                        var i = 0
                        while (i < total) {
                            val baseIdx = i * 4
                            val x = buf.get(baseIdx)
                            val y = buf.get(baseIdx + 1)
                            val z = buf.get(baseIdx + 2)
                            out.add(listOf(x, y, z))
                            i += step
                        }
                        out
                    } finally {
                        try { pc.release() } catch (_: Exception) { }
                    }
                } else {
                    emptyList()
                }

                hashMapOf<String, Any>(
                    "frame_id" to ("frm_" + frameCount),
                    "timestamp" to (System.currentTimeMillis() / 1000.0),
                    "rgb_base64" to rgbBase64,
                    "intrinsics" to mapOf(
                        "fx" to fx,
                        "fy" to fy,
                        "cx" to cx,
                        "cy" to cy,
                        "width" to w,
                        "height" to h
                    ),
                    "pose" to mapOf(
                        "position" to position,
                        "quaternion" to quaternion
                    ),
                    "point_cloud" to points
                )
            } catch (_: Exception) {
                null
            }
        }

        if (payload == null) return true // кадр не готов - не считаем это сетевой ошибкой

        // 2) Отправка
        val resp = try {
            api.streamData(sid, payload)
        } catch (_: Exception) {
            return false
        }

        if (!resp.isSuccessful) {
            return false
        }

        val body = resp.body() ?: return true

        withContext(Dispatchers.Main) {
            frameCount += 1
            val hints = body.ai_hints
            if (hints != null) {
                updateQualityUI(hints.quality_score)
                val msg = when {
                    !hints.warnings.isNullOrEmpty() -> hints.warnings.joinToString("\n")
                    !hints.instructions.isNullOrEmpty() -> hints.instructions.joinToString("\n")
                    else -> null
                }
                if (!msg.isNullOrBlank()) {
                    showHint(msg)
                }

                if (userMarkers.size >= MIN_POINTS_FOR_MODEL) {
                    btnAnalyze.isEnabled = true
                }
            }
        }

        return true
    }

    private fun stopStreaming() {
        isStreaming = false
        streamJob?.cancel()
        streamJob = null
    }

    private suspend fun doRequestModeling() {
        val sid = currentSessionId
        if (sid.isNullOrBlank()) {
            withContext(Dispatchers.Main) {
                showError("Сессия не активна")
                transitionTo(AppState.IDLE)
            }
            return
        }

        stopStreaming()

        try {
            // На всякий случай отправляем anchors
            syncAnchorsToServer()
        } catch (_: Exception) {
            // Ignore
        }

        val response = try {
            api.startModeling(sid)
        } catch (e: Exception) {
            withContext(Dispatchers.Main) {
                showError("Ошибка моделирования: " + (e.message ?: "UNKNOWN"))
                transitionTo(AppState.SCANNING)
            }
            return
        }

        if (!response.isSuccessful || response.body() == null) {
            withContext(Dispatchers.Main) {
                showError("Моделирование не удалось: HTTP " + response.code())
                transitionTo(AppState.SCANNING)
            }
            return
        }

        val model = response.body()!!
        withContext(Dispatchers.Main) {
            current3DModel = model
            selectedVariantIndex = 0
            transitionTo(AppState.SELECTING)

            // Подписи на кнопках вариантов
            val opts = model.options.orEmpty()
            btnVariant1.text = opts.getOrNull(0)?.variant_name ?: "Вариант 1"
            btnVariant2.text = opts.getOrNull(1)?.variant_name ?: "Вариант 2"
            btnVariant3.text = opts.getOrNull(2)?.variant_name ?: "Вариант 3"

            // Показать первый вариант
            visualizeScaffoldVariant(0)
        }
    }

    private fun placeAnchor() {
        if (userMarkers.size >= MAX_POINTS) {
            showHint("⚠️ Достигнут лимит точек")
            return
        }

        val frame = try {
            sceneView.arSession?.update()
        } catch (_: Exception) {
            null
        } ?: return

        val x = sceneView.width / 2f
        val y = sceneView.height / 2f

        val hit = frame.hitTest(x, y).firstOrNull { hitResult ->
            val trackable = hitResult.trackable
            (trackable is Plane) && trackable.isPoseInPolygon(hitResult.hitPose)
        }

        if (hit == null) {
            showHint("⚠️ Не найдено место для точки")
            return
        }

        val anchor = hit.createAnchor()
        val anchorNode = AnchorNode(anchor).apply {
            setParent(sceneView.scene)
        }

        // Маленький визуальный маркер
        val marker = Node().apply {
            parent = anchorNode
            localScale = Vector3(0.05f, 0.05f, 0.05f)
            renderable = ModelAssets.getCopy(ModelAssets.ModelType.WEDGE_NODE)
        }

        anchorNodes.add(anchorNode)

        val p = anchor.pose
        userMarkers.add(mapOf(
            "x" to p.tx(),
            "y" to p.ty(),
            "z" to p.tz()
        ))

        updatePointsCount()
        btnAnalyze.isEnabled = userMarkers.size >= MIN_POINTS_FOR_MODEL
        vibrate(35)

        // Синхронизируем anchors фоном
        scope.launch {
            try {
                syncAnchorsToServer()
            } catch (_: Exception) {
                // Ignore
            }
        }

        showHint("✓ Точка добавлена: ${userMarkers.size}")
    }


    private suspend fun sendLogEvent(event: String, data: Map<String, Any?> = emptyMap()) {
        val sid = currentSessionId ?: return
        runCatching {
            api.logEvent(
                sid,
                LogPayload(
                    event = event,
                    timestamp_ms = System.currentTimeMillis(),
                    data = data,
                    device = LogDeviceInfo(
                        model = Build.MODEL,
                        manufacturer = Build.MANUFACTURER,
                        sdk = Build.VERSION.SDK_INT
                    )
                )
            )
        }
    }

    private fun request3DReconstruction() {
        val option = current3DModel?.options?.getOrNull(selectedVariantIndex)
        val elements = option?.elements.orEmpty().ifEmpty { option?.full_structure.orEmpty() }

        if (elements.isEmpty()) {
            showHint("⚠️ Пока нет элементов для 3D превью")
            return
        }

        sceneBuilder.buildScene(elements)
        viewModel.saveSnapshot(elements, "Построена структура")
        transitionTo(AppState.PREVIEW_3D)
        showHint("✓ Построено элементов: ${elements.size}")
    }

    private fun hide3DPreview() {
        sceneBuilder.clearScene()
        show3DPreview = false
        showHint("👁️ Превью скрыто")
    }

    private fun visualizeScaffoldVariant(index: Int) {
        val option = current3DModel?.options?.getOrNull(index) ?: return
        val elements = option.elements.orEmpty().ifEmpty { option.full_structure.orEmpty() }
        if (elements.isNotEmpty()) {
            sceneBuilder.buildScene(elements)
            viewModel.saveSnapshot(elements, "Выбран вариант ${index + 1}")
        }
    }

    private fun showPhysicsHeatmap() {
        val option = current3DModel?.options?.getOrNull(selectedVariantIndex)
        val elements = option?.elements.orEmpty().ifEmpty { option?.full_structure.orEmpty() }
        if (elements.isEmpty()) {
            showHint("⚠️ Нет данных physics для отображения")
            return
        }

        val heatmap = elements.map {
            mapOf(
                "id" to it.id,
                "color" to (it.stress_color ?: "gray")
            )
        }
        sceneBuilder.updateColors(heatmap)
        showHint("📊 Карта нагрузок обновлена")
    }

    private fun showFinalResults(option: ScaffoldOption) {
        val score = option.safety_score
        val status = option.physics?.status ?: "UNKNOWN"
        showHint("🏁 Готово: safety $score%, physics=$status")
    }



    private fun handleStructureState(state: StructureState) {
        when (state) {
            is StructureState.Idle -> Unit
            is StructureState.Updating -> showLoadingIndicator()
            is StructureState.Updated -> {
                hideLoadingIndicator()
                handleUpdateResponse(state.response)
            }
            is StructureState.Error -> {
                hideLoadingIndicator()
                showError(state.message)
            }
        }
    }

    private fun handleUpdateResponse(response: UpdateResponse) {
        sceneBuilder.updateHeatmap(response.heatmap)

        if (viewModel.editMode.value == EditMode.SIMULATION) {
            if (response.collapsed.elements.isNotEmpty()) {
                physicsAnimator.animateFall(response.collapsed.elements)
                showCollapsedNotification(response.collapsed.elements.size)

                Handler(Looper.getMainLooper()).postDelayed({
                    response.collapsed.elements.forEach { elementId ->
                        sceneBuilder.removeElement(elementId)
                    }
                }, 2000)
            }
        } else if (response.collapsed.elements.isNotEmpty()) {
            highlightWouldCollapse(response.collapsed.elements)
        }

        if (!response.is_stable) {
            showWarning("⚠️ Структура нестабильна!")
        } else {
            hasRedZones = false
            btnAnalyze.animate().cancel()
            btnAnalyze.scaleX = 1.0f
            btnAnalyze.scaleY = 1.0f
        }
    }

    private fun onElementTapped(elementId: String) {
        viewModel.previewRemoveElement(elementId) { preview ->
            runOnUiThread {
                if (preview.is_critical) {
                    showConfirmDialog(
                        title = "⚠️ Критический элемент!",
                        message = preview.warning,
                        onConfirm = { removeElementWithAnimation(elementId) }
                    )
                } else {
                    removeElementWithAnimation(elementId)
                }
            }
        }
    }

    private fun removeElementWithAnimation(elementId: String) {
        viewModel.saveSnapshot(sceneBuilder.getAllElements(), "Удален $elementId")
        soundManager.play(SoundType.REMOVE)
        viewModel.removeElement(
            elementId = elementId,
            onSuccess = { response ->
                val removedIds = response.collapsed.elements.toSet() + elementId
                val nextElements = sceneBuilder.getAllElements().filterNot { it.id in removedIds }
                viewModel.saveSnapshot(nextElements, "Удален $elementId")
            },
            onError = { error ->
                runOnUiThread { showError("Не удалось удалить элемент: $error") }
            }
        )
    }

    private fun showLoadingIndicator() = showHint("⏳ Обновление структуры...")

    private fun hideLoadingIndicator() = Unit



    private fun toggleEyeOfAI() {
        if (eyeOfAIActive) {
            voxelVisualizer.hideVoxels()
            voxelLegend.visibility = View.GONE
            fabEyeOfAI.setImageResource(R.drawable.ic_eye)
            eyeOfAIActive = false
            soundManager.play(SoundType.WHOOSH, volume = 0.3f, pitch = 0.8f)
            return
        }

        val sessionId = currentSessionId
        if (sessionId.isNullOrBlank()) {
            showError("Сессия не активна. Сначала нажмите START")
            return
        }

        showLoadingDialog("Загрузка вокселей...")
        lifecycleScope.launch {
            try {
                val response = api.getVoxels(sessionId)
                if (response.isSuccessful && response.body() != null) {
                    val voxelResponse = response.body()!!
                    currentVoxelData = voxelResponse.voxels.map { v ->
                        VoxelData(
                            position = v.position,
                            type = v.type,
                            color = v.color,
                            alpha = v.alpha.toFloat(),
                            size = voxelResponse.resolution.toFloat(),
                            radius = v.radius
                        )
                    }

                    voxelVisualizer.showVoxels(currentVoxelData!!)
                    voxelLegend.visibility = View.VISIBLE
                    fabEyeOfAI.setImageResource(R.drawable.ic_eye_off)
                    eyeOfAIActive = true
                    soundManager.play(SoundType.WHOOSH, volume = 0.5f, pitch = 1.5f)
                    showToast("👁️ Теперь вы видите глазами ИИ! Вокселей: ${voxelResponse.total_count}")
                } else {
                    showError("Не удалось загрузить воксели")
                }
            } catch (e: Exception) {
                showError("Ошибка загрузки Eye of AI: ${e.message}")
            } finally {
                hideLoadingDialog()
            }
        }
    }

    private fun showLoadingDialog(message: String) {
        hideLoadingDialog()
        loadingDialog = AlertDialog.Builder(this)
            .setTitle("Подождите")
            .setMessage(message)
            .setCancelable(false)
            .create()
        loadingDialog?.show()
    }

    private fun hideLoadingDialog() {
        loadingDialog?.dismiss()
        loadingDialog = null
    }

    private fun showError(message: String) {
        showHint("❌ $message")
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    private fun showWarning(message: String) {
        Snackbar.make(findViewById(android.R.id.content), message, Snackbar.LENGTH_LONG)
            .setBackgroundTint(getColor(android.R.color.holo_orange_dark))
            .setTextColor(getColor(android.R.color.white))
            .show()
        showHint(message)
    }

    private fun highlightWouldCollapse(elementIds: List<String>) {
        hasRedZones = elementIds.isNotEmpty()
        if (hasRedZones) {
            startPlayButtonPulse()
        }
        showHint("⚠️ Могут упасть элементы: ${elementIds.size}")
        elementIds.forEach { id ->
            sceneBuilder.findNodeById(id)?.let { node ->
                animateBlink(node, SceneColor(android.graphics.Color.RED))
            }
        }
    }

    private fun animateBlink(node: Node, color: SceneColor) {
        val animator = ValueAnimator.ofFloat(0f, 1f)
        animator.duration = 500
        animator.repeatCount = 3
        animator.repeatMode = ValueAnimator.REVERSE
        animator.addUpdateListener {
            val alpha = it.animatedValue as Float
            node.localScale = Vector3.one().scaled(1f + alpha * 0.05f)
        }
        animator.start()
    }

    private fun showCollapsedNotification(count: Int) {
        val message = when {
            count == 1 -> "💥 1 элемент обрушился!"
            count < 5 -> "💥 $count элемента обрушились!"
            else -> "💥 $count элементов обрушились!"
        }
        Snackbar.make(findViewById(android.R.id.content), message, Snackbar.LENGTH_SHORT)
            .setBackgroundTint(getColor(android.R.color.holo_red_dark))
            .setTextColor(getColor(android.R.color.white))
            .show()

        val vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(VibrationEffect.createOneShot(300, VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(300)
        }
    }

    private fun showConfirmDialog(title: String, message: String, onConfirm: () -> Unit) {
        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(message)
            .setPositiveButton("Удалить") { _, _ -> onConfirm() }
            .setNegativeButton("Отмена", null)
            .setIcon(android.R.drawable.ic_dialog_alert)
            .show()
    }

    private fun updateModeUI(mode: EditMode) {
        modeIndicator.animate()
            .alpha(0f)
            .scaleX(0.8f)
            .scaleY(0.8f)
            .setDuration(100)
            .withEndAction {
                when (mode) {
                    EditMode.EDIT -> {
                        modeIndicator.setBackgroundResource(R.drawable.mode_edit_bg)
                        modeIcon.text = "✏️"
                        modeText.text = "Режим редактирования"
                        tvModeStatus.text = "MODE: EDIT"
                        soundManager.play(SoundType.WHOOSH, volume = 0.3f, pitch = 1.2f)
                        physicsAnimator.stopAll()
                    }
                    EditMode.SIMULATION -> {
                        modeIndicator.setBackgroundResource(R.drawable.mode_simulation_bg)
                        modeIcon.text = "⚡"
                        modeText.text = "Режим симуляции"
                        tvModeStatus.text = "MODE: SIMULATION"
                        soundManager.play(SoundType.WHOOSH, volume = 0.5f, pitch = 0.8f)
                        vibrateShort()
                        checkStructureStability()
                    }
                }

                modeIndicator.animate()
                    .alpha(1f)
                    .scaleX(1f)
                    .scaleY(1f)
                    .setDuration(150)
                    .start()
            }
            .start()
    }

    private fun startPlayButtonPulse() {
        btnAnalyze.animate()
            .scaleX(1.1f)
            .scaleY(1.1f)
            .setDuration(500)
            .withEndAction {
                btnAnalyze.animate()
                    .scaleX(1.0f)
                    .scaleY(1.0f)
                    .setDuration(500)
                    .withEndAction {
                        if (hasRedZones) {
                            startPlayButtonPulse()
                        }
                    }
                    .start()
            }
            .start()
    }

    private fun vibrateShort() {
        val vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        if (!vibrator.hasVibrator()) {
            return
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(VibrationEffect.createOneShot(70, 120))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(70)
        }
    }

    private fun checkStructureStability() {
        viewModel.removeElement(
            elementId = "__CHECK_ONLY__",
            onSuccess = { response ->
                if (response.collapsed.elements.isNotEmpty()) {
                    showWarning(
                        "⚠️ Обнаружено ${response.collapsed.elements.size} висящих элементов!\nОни будут удалены при первом изменении."
                    )
                    highlightWouldCollapse(response.collapsed.elements)
                }
            },
            onError = { }
        )
    }

    private fun updateUndoRedoButtons() {
        btnUndo.isEnabled = viewModel.canUndo()
        btnRedo.isEnabled = viewModel.canRedo()
        if (viewModel.canUndo()) {
            val description = viewModel.getUndoDescription()
            btnUndo.tooltipText = "Отменить: $description"
        }
    }

    private fun performUndo() {
        viewModel.undo { snapshot ->
            sceneBuilder.buildScene(snapshot.elements)
            showToast("↶ Отменено: ${snapshot.description}")
        }
    }

    private fun performRedo() {
        viewModel.redo { snapshot ->
            sceneBuilder.buildScene(snapshot.elements)
            showToast("↷ Повторено: ${snapshot.description}")
        }
    }

    private fun showToast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.edit_menu, menu)

        lifecycleScope.launch {
            viewModel.editMode.collect { mode ->
                menu.findItem(R.id.action_toggle_mode)?.title = when (mode) {
                    EditMode.EDIT -> "🎬 Режим: EDIT"
                    EditMode.SIMULATION -> "⚡ Режим: SIMULATION"
                }
            }
        }

        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_toggle_mode -> {
                viewModel.toggleEditMode()
                true
            }
            R.id.action_layers -> {
                showLayersDialog()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    private fun clearARAnchors() {
        anchorNodes.forEach { it.anchor?.detach(); it.setParent(null) }
        anchorNodes.clear()
        sceneBuilder.clearScene()
    }
}
