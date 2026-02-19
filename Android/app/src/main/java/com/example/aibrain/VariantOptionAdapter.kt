package com.example.aibrain

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.card.MaterialCardView

class VariantOptionAdapter(
    private var items: List<ScaffoldOption> = emptyList(),
    private var selectedIndex: Int = 0,
    private val onSelect: (Int) -> Unit,
) : RecyclerView.Adapter<VariantOptionAdapter.VH>() {
    fun submit(newItems: List<ScaffoldOption>, selected: Int = 0) {
        items = newItems
        selectedIndex = selected.coerceIn(0, maxOf(0, items.size - 1))
        notifyDataSetChanged()
    }

    fun setSelected(index: Int) {
        val prev = selectedIndex
        selectedIndex = index
        if (prev in items.indices) notifyItemChanged(prev)
        if (selectedIndex in items.indices) notifyItemChanged(selectedIndex)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = LayoutInflater.from(parent.context).inflate(R.layout.item_variant_option, parent, false)
        return VH(v, onSelect)
    }

    override fun getItemCount(): Int = items.size

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(items[position], position == selectedIndex, position)
    }

    class VH(itemView: View, private val onSelect: (Int) -> Unit) : RecyclerView.ViewHolder(itemView) {
        private val card: MaterialCardView = itemView.findViewById(R.id.card_root)
        private val tvTitle: TextView = itemView.findViewById(R.id.tv_title)
        private val tvSafety: TextView = itemView.findViewById(R.id.tv_safety)
        private val tvWeight: TextView = itemView.findViewById(R.id.tv_weight)
        private val tvStats: TextView = itemView.findViewById(R.id.tv_stats)
        private val tvPreview: TextView = itemView.findViewById(R.id.tv_preview)

        fun bind(opt: ScaffoldOption, selected: Boolean, index: Int) {
            tvTitle.text = opt.variant_name.ifBlank { "Variant ${index + 1}" }
            tvSafety.text = "Safety: ${opt.safety_score}%"
            tvWeight.text = opt.stats?.total_weight_kg?.let { "Weight: ${it}kg" } ?: "Weight: --"
            tvStats.text = "Beams: ${opt.stats?.total_beams ?: "--"} | Nodes: ${opt.stats?.total_nodes ?: "--"}"
            tvPreview.text = opt.ai_critique?.firstOrNull()?.trim().orEmpty()

            if (selected) {
                card.strokeWidth = 2
                card.strokeColor = 0xFF00F5FF.toInt()
                card.setCardBackgroundColor(0x3321D4FF)
            } else {
                card.strokeWidth = 1
                card.strokeColor = 0x3300F5FF
                card.setCardBackgroundColor(0x1A0A101A)
            }
            card.setOnClickListener { onSelect(index) }
        }
    }
}
