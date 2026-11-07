<template>
  <div class="model-config">
    <header class="page-header glass-card">
      <div>
        <h2 class="text-glow-soft">模型配置</h2>
        <div class="header-info">配置各业务环节使用的模型，保存后立即生效</div>
      </div>
      <div class="actions">
        <button class="btn btn-xs" :disabled="loading || saving" @click="loadConfig">
          {{ loading ? "加载中" : "重新加载" }}
        </button>
        <button class="btn btn-xs" :disabled="loading || saving" @click="restoreDefaults">
          恢复环境默认
        </button>
        <button class="btn btn-xs primary" :disabled="loading || saving" @click="saveConfig">
          {{ saving ? "保存中" : "保存配置" }}
        </button>
      </div>
    </header>

    <nav class="monitor-tabs" aria-label="监测台页面">
      <router-link to="/observability" exact-active-class="active">监控概览</router-link>
      <router-link to="/observability/models" active-class="active">模型配置</router-link>
    </nav>

    <div v-if="message" class="message" :class="{ error: isError }" role="status">{{ message }}</div>

    <section class="chain-section glass-card">
      <div class="section-header">
        <div class="section-title">模型降级链</div>
        <div class="chain-actions">
          <button class="btn btn-xs" @click="loadChain" :disabled="chainLoading">{{ chainLoading ? "加载中" : "重新加载" }}</button>
          <button class="btn btn-xs" @click="saveChain" :disabled="chainSaving">{{ chainSaving ? "保存中" : "保存" }}</button>
        </div>
      </div>
      <div class="chain-hint">主模型失败（限流/超时/5xx/模型不存在/额度用尽）时按顺序自动降级；每行填一个模型名，第一行为主模型。留空=回退环境中的主模型。<br />候选：点模型名加入下方输入框；点 × 从候选删去（立即保存，不影响已在链上的模型）。</div>
      <textarea
        v-model="chainText"
        class="chain-input"
        rows="4"
        placeholder="qwen3.8-max-0902&#10;qwen3.8-27b&#10;qwen3.8-flash"
        spellcheck="false"
      ></textarea>
      <div class="chain-candidates">
        <span class="chain-candidate-label">候选：</span>
        <span v-for="c in chainCandidates" :key="c" class="chain-chip">
          <span class="chain-chip-name" @click="addCandidate(c)" :title="`加入降级链：${c}`">{{ c }}</span>
          <button
            class="chain-chip-del"
            :disabled="candidateSaving"
            @click="removeCandidate(c)"
            :title="`从候选删去 ${c}（不影响降级链）`"
          >×</button>
        </span>
        <span v-if="!chainCandidates.length" class="chain-candidate-empty">（暂无候选，可手动添加或点「恢复默认」）</span>
        <span class="chain-candidate-add">
          <input
            v-model="newCandidate"
            class="chain-candidate-input"
            placeholder="添加候选模型名"
            spellcheck="false"
            @keyup.enter="addNewCandidate"
          />
          <button class="btn btn-xs" :disabled="candidateSaving || !newCandidate.trim()" @click="addNewCandidate">添加</button>
          <button
            class="btn btn-xs"
            :disabled="candidateSaving || !chainDefaults.length || sameCandidates(chainCandidates, chainDefaults)"
            @click="restoreDefaultCandidates"
          >恢复默认</button>
        </span>
      </div>
      <div v-if="chainOrder.length" class="chain-summary">
        当前生效链：<span v-for="(m, i) in chainOrder" :key="m + i" class="chain-item">{{ i + 1 }}. {{ m }}</span>
      </div>
      <div v-if="chainMessage" class="chain-message" :class="{ 'chain-error': chainError }">{{ chainMessage }}</div>
    </section>

    <section class="config-grid">
      <article v-for="group in groups" :key="group.key" class="config-card glass-card">
        <div class="group-icon">{{ group.icon }}</div>
        <div class="group-content">
          <label :for="group.key">{{ group.label }}</label>
          <p>{{ group.description }}</p>
          <input
            :id="group.key"
            v-model="models[group.key]"
            class="model-input"
            :placeholder="group.placeholder"
            spellcheck="false"
            maxlength="64"
            autocomplete="off"
          />
          <div v-if="group.key === 'decompose_model' || group.key === 'reviewer_model' || group.key === 'sub_app_model'" class="field-hint">
            留空时使用主问答模型：{{ mainModel || "环境变量 DASHSCOPE_MODEL" }}
          </div>
          <div v-else class="field-hint">当前环境默认：{{ defaults[group.key] || "未配置" }}</div>
        </div>
      </article>
    </section>

    <div class="save-footer">
      <span>修改模型名不会变更 API 密钥。请确保对应模型已在服务商侧开通。</span>
      <button class="btn btn-xs primary" :disabled="loading || saving" @click="saveConfig">
        {{ saving ? "保存中" : "保存并生效" }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import {
  getLlmChain,
  getModelRoleConfig,
  updateLlmCandidates,
  updateLlmChain,
  updateModelRoleConfig,
  type ModelRoleConfig,
} from "../api"

type ModelKey = keyof ModelRoleConfig
const models = reactive<ModelRoleConfig>({
  decompose_model: "",
  reviewer_model: "",
  sub_app_model: "",
  asr_model: "",
  tts_model: "",
  tts_voice: "",
})
const defaults = reactive<ModelRoleConfig>({
  decompose_model: "",
  reviewer_model: "",
  sub_app_model: "",
  asr_model: "",
  tts_model: "",
  tts_voice: "",
})
const mainModel = ref("")
const loading = ref(false)
const saving = ref(false)
const message = ref("")
const isError = ref(false)

const chainText = ref("")
const chainOrder = ref<string[]>([])
const chainCandidates = ref<string[]>([])
const chainLoading = ref(false)
const chainSaving = ref(false)
const chainMessage = ref("")
const chainError = ref(false)
const newCandidate = ref("")
const candidateSaving = ref(false)
const chainDefaults = ref<string[]>([])

const groups: { key: ModelKey; label: string; description: string; placeholder: string; icon: string }[] = [
  { key: "decompose_model", label: "意图拆解", description: "分析用户问题并拆分命理问答任务。", placeholder: "留空使用主问答模型", icon: "意" },
  { key: "reviewer_model", label: "审核模型", description: "审核生成答案中的事实与表达质量。", placeholder: "留空使用主问答模型", icon: "审" },
  { key: "sub_app_model", label: "子应用解读", description: "供塔罗、紫微、六爻、合婚等子应用生成解读。", placeholder: "留空使用主问答模型", icon: "解" },
  { key: "asr_model", label: "语音识别（ASR）", description: "将用户录音转换为文本。", placeholder: "例如 qwen-audio-3.1-asr-flash", icon: "听" },
  { key: "tts_model", label: "语音朗读（TTS）模型", description: "将回答文本合成为语音。", placeholder: "例如 qwen-audio-3.1-tts-flash", icon: "读" },
  { key: "tts_voice", label: "语音朗读音色", description: "TTS 使用的音色标识。", placeholder: "例如 longanhuan_v3.1", icon: "声" },
]

async function loadConfig() {
  loading.value = true
  message.value = ""
  try {
    const result = await getModelRoleConfig()
    Object.assign(models, result.models)
    Object.assign(defaults, result.defaults)
    mainModel.value = result.main_model
    isError.value = false
  } catch (error) {
    isError.value = true
    message.value = error instanceof Error ? error.message : "获取模型配置失败"
  } finally {
    loading.value = false
  }
}

function restoreDefaults() {
  Object.assign(models, defaults)
  message.value = "已恢复环境默认值，点击保存后生效"
  isError.value = false
}

async function saveConfig() {
  saving.value = true
  message.value = ""
  try {
    const result = await updateModelRoleConfig({ ...models })
    Object.assign(models, result.models)
    Object.assign(defaults, result.defaults)
    message.value = "配置已保存并生效"
    isError.value = false
  } catch (error) {
    isError.value = true
    message.value = error instanceof Error ? error.message : "保存配置失败"
  } finally {
    saving.value = false
  }
}

async function loadChain() {
  chainLoading.value = true
  chainError.value = false
  try {
    const data = await getLlmChain()
    chainOrder.value = data.models
    chainCandidates.value = data.candidates
    chainDefaults.value = data.default_candidates || []
    chainText.value = data.models.join("\n")
    chainMessage.value = ""
  } catch (error) {
    chainError.value = true
    chainMessage.value = error instanceof Error ? error.message : "获取降级链失败"
  } finally {
    chainLoading.value = false
  }
}

async function saveChain() {
  const models = chainText.value.split("\n").map((s) => s.trim()).filter(Boolean)
  chainSaving.value = true
  chainError.value = false
  try {
    const data = await updateLlmChain(models)
    chainOrder.value = data.models
    chainText.value = data.models.join("\n")
    chainMessage.value = "已保存并生效"
  } catch (error) {
    chainError.value = true
    chainMessage.value = error instanceof Error ? error.message : "保存失败"
  } finally {
    chainSaving.value = false
  }
}

function addCandidate(name: string) {
  const current = chainText.value.split("\n").map((s) => s.trim()).filter(Boolean)
  if (!current.includes(name)) {
    current.push(name)
    chainText.value = current.join("\n")
  }
}

function sameCandidates(a: string[], b: string[]) {
  return a.length === b.length && a.every((x, i) => x === b[i])
}

async function persistCandidates(next: string[], okText: string) {
  candidateSaving.value = true
  chainError.value = false
  try {
    const data = await updateLlmCandidates(next)
    chainCandidates.value = data.candidates
    chainMessage.value = okText
  } catch (error) {
    chainError.value = true
    chainMessage.value = error instanceof Error ? error.message : "候选保存失败"
  } finally {
    candidateSaving.value = false
  }
}

function removeCandidate(name: string) {
  if (candidateSaving.value) return
  const next = chainCandidates.value.filter((c) => c !== name)
  persistCandidates(next, next.length ? `已从候选删去 ${name}` : `已删去 ${name}，候选已清空`)
}

function addNewCandidate() {
  const name = newCandidate.value.trim()
  if (!name || candidateSaving.value) return
  if (chainCandidates.value.includes(name)) {
    chainError.value = true
    chainMessage.value = `${name} 已在候选中`
    return
  }
  newCandidate.value = ""
  persistCandidates([...chainCandidates.value, name], `已添加候选 ${name}`)
}

function restoreDefaultCandidates() {
  if (candidateSaving.value || !chainDefaults.value.length) return
  persistCandidates([...chainDefaults.value], "已恢复默认候选")
}

onMounted(() => {
  loadConfig()
  loadChain()
})
</script>

<style scoped>
.model-config {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  max-width: 1180px;
  margin: 0 auto;
  padding: var(--spacing-lg);
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
  padding: var(--spacing-lg);
}
.page-header h2 { margin: 0; font-size: 20px; }
.header-info, .config-card p, .field-hint, .save-footer { color: var(--text-dim); font-size: 12px; }
.header-info { margin-top: 5px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.btn.primary { color: var(--accent-light); border-color: var(--accent-light); }
.monitor-tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--border); }
.monitor-tabs a {
  padding: 9px 14px;
  color: var(--text-dim);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  font-size: 13px;
}
.monitor-tabs a:hover, .monitor-tabs a.active { color: var(--accent-light); border-bottom-color: var(--accent-light); }
.config-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--spacing-md); }
.config-card { display: flex; gap: var(--spacing-md); padding: var(--spacing-lg); }
.group-icon {
  display: grid;
  place-items: center;
  flex: 0 0 38px;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  color: var(--accent-light);
  background: rgba(212, 175, 55, 0.12);
  font-weight: 700;
}
.group-content { min-width: 0; flex: 1; }
.group-content label { font-size: 14px; font-weight: 600; }
.config-card p { margin: 6px 0 12px; line-height: 1.5; }
.model-input {
  box-sizing: border-box;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 6px);
  background: var(--bg-bright, rgba(255, 255, 255, 0.04));
  color: var(--text);
  font: 13px var(--font-mono, monospace);
}
.model-input:focus { outline: none; border-color: var(--accent, #d4af37); }
.field-hint { margin-top: 7px; }
.message { padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-sm, 6px); color: var(--success, #1dc981); font-size: 13px; }
.message.error { color: var(--danger, #e8463a); }
.chain-section { padding: var(--spacing-lg); border-radius: var(--radius); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--spacing-md); }
.section-title { font-size: 15px; font-weight: 600; }
.chain-actions { display: flex; gap: var(--spacing-md); }
.chain-hint { font-size: 12px; color: var(--text-dim); margin-bottom: var(--spacing-md); line-height: 1.6; }
.chain-input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg-bright, rgba(255, 255, 255, 0.04));
  color: var(--text);
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  resize: vertical;
}
.chain-input:focus { outline: none; border-color: var(--accent, #d4af37); }
.chain-candidates { display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-8, 8px); margin-top: var(--spacing-md); }
.chain-candidate-label, .chain-candidate-empty { font-size: 12px; color: var(--text-dim); }
.chain-candidate-empty { font-style: italic; }
.chain-candidate-add { display: inline-flex; align-items: center; gap: 6px; }
.chain-candidate-input {
  width: 160px;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
}
.chain-candidate-input:focus { outline: none; border-color: var(--accent, #d4af37); }
.chain-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 2px 4px 2px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--text-dim);
  transition: all 0.15s ease;
}
.chain-chip:hover { color: var(--text); border-color: var(--accent, #d4af37); }
.chain-chip-name { cursor: pointer; }
.chain-chip-del {
  border: none;
  background: transparent;
  color: inherit;
  font-size: 13px;
  line-height: 1;
  padding: 0 3px;
  border-radius: 999px;
  cursor: pointer;
  opacity: 0.6;
}
.chain-chip-del:hover:not(:disabled) { color: #e06c75; opacity: 1; }
.chain-chip-del:disabled { cursor: not-allowed; opacity: 0.3; }
.chain-summary { display: flex; flex-wrap: wrap; gap: var(--spacing-md); align-items: center; margin-top: var(--spacing-md); font-size: 12px; color: var(--text-dim); }
.chain-item {
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--bg-bright, rgba(255, 255, 255, 0.06));
  font-family: var(--font-mono, monospace);
  color: var(--text);
}
.chain-message { margin-top: var(--spacing-md); font-size: 12px; color: var(--success, #1dc981); }
.chain-message.chain-error { color: var(--danger, #e8463a); }
.save-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
@media (max-width: 720px) {
  .model-config { padding: var(--spacing-md); }
  .page-header { align-items: flex-start; flex-direction: column; }
  .section-header { align-items: flex-start; flex-direction: column; gap: var(--spacing-sm); }
  .config-grid { grid-template-columns: 1fr; }
  .save-footer { align-items: flex-start; flex-direction: column; }
}
</style>
