package com.example.aibrain

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/**
 * ViewModel для управления состоянием структуры и взаимодействия с API.
 */
class StructureViewModel(
    private val apiService: ApiService
) : ViewModel() {

    private val _editMode = MutableStateFlow(EditMode.EDIT)
    val editMode: StateFlow<EditMode> = _editMode

    private val _structureState = MutableStateFlow<StructureState>(StructureState.Idle)
    val structureState: StateFlow<StructureState> = _structureState

    private var currentSessionId: String? = null

    fun setSessionId(sessionId: String) {
        currentSessionId = sessionId
    }

    fun toggleEditMode() {
        _editMode.value = when (_editMode.value) {
            EditMode.EDIT -> EditMode.SIMULATION
            EditMode.SIMULATION -> EditMode.EDIT
        }
    }

    /**
     * Предварительный просмотр: что произойдет если удалить элемент.
     */
    fun previewRemoveElement(elementId: String, onResult: (PreviewResponse) -> Unit) {
        val sessionId = currentSessionId ?: return

        viewModelScope.launch {
            try {
                val response = apiService.previewRemove(sessionId, elementId)
                if (response.isSuccessful && response.body() != null) {
                    onResult(response.body()!!)
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    /**
     * Удалить элемент из структуры.
     */
    fun removeElement(
        elementId: String,
        onSuccess: (UpdateResponse) -> Unit,
        onError: (String) -> Unit
    ) {
        val sessionId = currentSessionId ?: run {
            onError("No active session")
            return
        }

        _structureState.value = StructureState.Updating

        viewModelScope.launch {
            try {
                val action = UpdateAction(
                    action = "REMOVE",
                    element_id = elementId
                )

                val response = apiService.updateStructure(sessionId, action)

                if (response.isSuccessful && response.body() != null) {
                    val updateResponse = response.body()!!
                    _structureState.value = StructureState.Updated(updateResponse)
                    onSuccess(updateResponse)
                } else {
                    val errorMsg = "Server error: ${response.code()}"
                    _structureState.value = StructureState.Error(errorMsg)
                    onError(errorMsg)
                }
            } catch (e: Exception) {
                val errorMsg = e.message ?: "Unknown error"
                _structureState.value = StructureState.Error(errorMsg)
                onError(errorMsg)
            }
        }
    }

    /**
     * Добавить элемент в структуру.
     */
    fun addElement(
        element: ScaffoldElement,
        onSuccess: (UpdateResponse) -> Unit,
        onError: (String) -> Unit
    ) {
        val sessionId = currentSessionId ?: run {
            onError("No active session")
            return
        }

        _structureState.value = StructureState.Updating

        viewModelScope.launch {
            try {
                val action = UpdateAction(
                    action = "ADD",
                    element_data = element
                )

                val response = apiService.updateStructure(sessionId, action)

                if (response.isSuccessful && response.body() != null) {
                    val updateResponse = response.body()!!
                    _structureState.value = StructureState.Updated(updateResponse)
                    onSuccess(updateResponse)
                } else {
                    val errorMsg = "Server error: ${response.code()}"
                    _structureState.value = StructureState.Error(errorMsg)
                    onError(errorMsg)
                }
            } catch (e: Exception) {
                val errorMsg = e.message ?: "Unknown error"
                _structureState.value = StructureState.Error(errorMsg)
                onError(errorMsg)
            }
        }
    }
}

enum class EditMode {
    EDIT,
    SIMULATION
}

sealed class StructureState {
    object Idle : StructureState()
    object Updating : StructureState()
    data class Updated(val response: UpdateResponse) : StructureState()
    data class Error(val message: String) : StructureState()
}
