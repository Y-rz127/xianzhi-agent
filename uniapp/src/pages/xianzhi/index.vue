<template>
  <view class="page" :class="themeClass">
    <view class="meteor meteor-1" v-if="themeClass === 't-dark'"></view>
    <view class="meteor meteor-2" v-if="themeClass === 't-dark'"></view>
    <view class="meteor meteor-3" v-if="themeClass === 't-dark'"></view>
    <!-- 水墨山水背景 -->
    <view class="landscape" aria-hidden="true">
      <view class="mountain mountain-far"></view>
      <view class="mountain mountain-mid"></view>
      <view class="mountain-mist"></view>
      <view class="mountain mountain-near"></view>
      <!-- 飞鸟 -->
      <view class="bird bird-1"></view>
      <view class="bird bird-2"></view>
      <view class="bird bird-3"></view>
      <!-- 落款印章 -->
      <!-- <view class="seal">易</view> -->
    </view>

    <!-- 状态栏占位 -->
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <!-- 顶部头：汉堡(左) + 标题 + 命盘 -->
    <view class="header">
      <view class="header-top">
        <view class="header-left">
          <text class="icon-btn" @tap="openHistoryDrawer">☰</text>
          <text class="header-title display-font">先知</text>
          <text v-if="chartData" class="icon-btn bazi-btn" @tap="openBaziModal">☯</text>
        </view>
      </view>
    </view>

    <!-- 出生信息玻璃面板 -->
    <view class="birth-panel">
      <view class="birth-bar" @tap="showBirth = !showBirth">
        <view class="birth-bar-left">
          <text class="birth-icon">✦</text>
          <text class="birth-summary">{{ birthSummary }}</text>
        </view>
        <text class="arrow">{{ showBirth ? '▲' : '▼' }}</text>
      </view>
      <view v-if="showBirth" class="birth-form">
        <view class="form-row">
          <text class="label">出生日期</text>
          <picker mode="date" :value="birthDate" :end="today" @change="onDateChange">
            <view class="picker">
              <text class="picker-text">{{ birthDate || '选择日期' }}</text>
              <text class="picker-icon">▤</text>
            </view>
          </picker>
        </view>
        <view class="form-row">
          <text class="label">出生时辰</text>
          <picker mode="time" :value="birthTime" @change="onTimeChange">
            <view class="picker">
              <text class="picker-text">{{ birthTime || '选择时间' }}</text>
              <text class="picker-icon">◷</text>
            </view>
          </picker>
        </view>
        <view class="form-row">
          <text class="label">性别</text>
          <view class="seg-group">
            <text :class="['seg', gender === '男' && 'active']" @tap="gender = '男'">男</text>
            <text :class="['seg', gender === '女' && 'active']" @tap="gender = '女'">女</text>
          </view>
        </view>
        <view class="form-row">
          <text class="label">出生地</text>
          <view class="picker place-picker" @tap="showRegionPicker = true">
            <text class="picker-text">{{ birthPlace || '选择地点（校准真太阳时）' }}</text>
            <text class="picker-icon">📍</text>
          </view>
          <text v-if="solarTimeOffset !== 0" class="solar-hint">
            真太阳时{{ solarTimeOffset > 0 ? '+' : '' }}{{ solarTimeOffset }}分
          </text>
        </view>
        <view class="sect-hint">
          排盘引擎默认为晚子时（子正换日，23:00~24:00 算次日）
        </view>
        <view class="legal-link" @tap="goDisclaimer">查看免责声明 ›</view>
      </view>
    </view>

    <!-- 消息列表 -->
    <scroll-view class="messages" scroll-y :scroll-top="scrollTop" scroll-with-animation @scroll="onMsgScroll" :style="messagesStyle">
      <view v-if="!messages.length" class="empty-state">
        <view class="empty-avatar display-font">易</view>
        <text class="empty-title">先知命理</text>
        <text class="empty-desc">说出你的疑问，或报上生辰开启推演</text>
      </view>

      <view v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
        <view class="avatar display-font">{{ msg.role === 'assistant' ? '易' : '我' }}</view>
        <view class="msg-body">
          <!-- 排盘可视化组件：优先用后端直排盘数据（保证四柱完整），否则从回答文本解析 -->

          <view class="msg-text" :class="{ thinking: isThinking(msg.content) }">
            <MarkdownRender v-if="msg.role === 'assistant' && msg.content" :content="formatContent(msg.content)" />
            <text v-else-if="!msg.content" class="typing">推演中…</text>
            <text v-else>{{ formatContent(msg.content) }}</text>
          </view>
          <!-- 回答反馈栏（点赞/点踩） -->
          <view v-if="msg.role === 'assistant' && msg.content && !isThinking(msg.content)" class="feedback-bar">
            <text
              :class="['feedback-chip', feedbackState[msgFeedbackKey(msg, i)] === 'up' && 'active-up']"
              @tap="openFeedbackModal(msg, i, 'up')"
            >✓</text>
            <text
              :class="['feedback-chip', feedbackState[msgFeedbackKey(msg, i)] === 'down' && 'active-down']"
              @tap="openFeedbackModal(msg, i, 'down')"
            >✗</text>
            <text v-if="feedbackState[msgFeedbackKey(msg, i)] === 'saved'" class="feedback-saved">已记录</text>
          </view>
        </view>
      </view>
    </scroll-view>

    <!-- 回到底部悬浮按钮 -->
    <view v-if="showScrollBottom" class="scroll-bottom-btn" @tap="scrollToBottom">
      <text class="scroll-bottom-icon">↓</text>
    </view>

    <!-- 输入栏 -->
    <view class="input-bar" :style="inputBarStyle">
      <view class="input-wrap">
        <textarea
          class="input"
          v-model="inputText"
          :placeholder="placeholderText"
          placeholder-class="input-placeholder"
          :auto-height="true"
          :show-confirm-bar="false"
          :cursor-spacing="20"
          :adjust-position="false"
          confirm-type="send"
          @confirm="onSend"
          @focus="onInputFocus"
        />
      </view>
      <view :class="['voice-btn', (thinking || voiceBusy) && 'disabled']" @tap="toggleVoice">
        <text v-if="!recording && !voiceBusy" class="voice-text">🎤</text>
        <text v-else-if="recording" class="voice-text recording-pulse">●</text>
        <text v-else class="voice-text busy-bounce">⏳</text>
      </view>
      <view
        :class="['send-btn', (thinking || !inputText.trim()) && 'disabled']"
        @tap="onSend"
      >
        <text class="send-icon">➤</text>
      </view>
    </view>

    <!-- 命盘详情弹窗 -->
    <BaziModal
      :visible="showBaziModal"
      :pillars="modalPillars"
      :wuxing="modalWuxing"
      :dayun="modalDayun"
      :liunian="chartData?.liunian || []"
      :shensha="modalShensha"
      :analysis="chartData?.analysis"
      :startYun="chartData?.startYun"
      :warnings="chartData?.warnings || []"
      :birthTime="lastBirthInfo?.time"
      :gender="lastBirthInfo?.gender"
      :mingGong="chartData?.mingGong"
      :shenGong="chartData?.shenGong"
      @close="showBaziModal = false"
    />

    <!-- 历史会话抽屉 -->
    <view v-if="showHistoryDrawer" class="drawer-mask" @tap="closeHistoryDrawer">
      <view class="drawer-panel" @tap.stop :style="{ paddingTop: (statusBarHeight + 10) + 'px', width: drawerWidth + 'rpx' }">
        <!-- 拖拽手柄 -->
        <view class="drawer-resize-handle"
          @touchstart.stop.prevent="onResizeStart"
          @touchmove.stop.prevent="onResizeMove"
          @touchend.stop.prevent="onResizeEnd"
          @mousedown.stop.prevent="onResizeStart"
        >
          <view class="resize-indicator"></view>
        </view>
        <!-- 用户区：头像 + 昵称 -->
        <view class="drawer-profile" @tap="goMine">
          <view class="drawer-avatar">{{ avatarText }}</view>
          <view class="drawer-profile-info">
            <text class="drawer-nickname">{{ nickname }}</text>
            <text class="drawer-profile-sub">{{ isLoggedIn() ? '我的档案 ›' : '点击登录 ›' }}</text>
          </view>
          <view class="drawer-settings-btn" :style="{ top: (statusBarHeight - 45) + 'px' }" @tap.stop="goSettings">
            <text class="dq-icon">⚙</text>
          </view>
        </view>
        <!-- 快捷功能：横向滑动，一屏三个 -->
        <scroll-view class="drawer-quick-scroll" scroll-x :show-scrollbar="false">
          <view class="drawer-quick">
            <view class="drawer-quick-btn" @tap="goHehun">
              <text class="dq-icon">合</text><text>合婚</text>
            </view>
            <view class="drawer-quick-btn" @tap="goTarot">
              <text class="dq-icon">塔</text><text>塔罗</text>
            </view>
            <view class="drawer-quick-btn" @tap="goLiuYao">
              <text class="dq-icon">卦</text><text>六爻</text>
            </view>
            <view class="drawer-quick-btn" @tap="goHuangLi">
              <text class="dq-icon">历</text><text>黄历</text>
            </view>
          </view>
        </scroll-view>
        <view class="drawer-header">
          <text class="drawer-title">历史会话</text>
          <text class="drawer-close" @tap="closeHistoryDrawer">✕</text>
        </view>
        <view v-if="historyLoading" class="drawer-loading">加载中…</view>
        <view v-else-if="historySessions.length === 0" class="drawer-empty">暂无历史会话</view>
        <scroll-view v-else scroll-y class="drawer-list">
          <view
            v-for="s in historySessions"
            :key="s.id"
            :class="['drawer-item', s.id === conversationId && 'active']"
            @tap="switchToSession(s)"
          >
            <view class="drawer-item-top">
              <text class="drawer-item-title">{{ s.title || '新会话' }}</text>
              <text class="drawer-item-del" @tap.stop="deleteHistorySession(s.id)">✕</text>
            </view>
            <text class="drawer-item-msg">{{ s.lastMessage || '（暂无消息）' }}</text>
            <view class="drawer-item-meta">
              <text class="drawer-item-time">{{ formatSessionTime(s.lastTime) }}</text>
              <text class="drawer-item-count">{{ s.messageCount }} 条</text>
            </view>
          </view>
        </scroll-view>
        <view class="drawer-footer">
          <text class="drawer-new-btn" @tap="closeHistoryDrawer(); newSession()">+ 新建会话</text>
        </view>
      </view>
    </view>

    <!-- 反馈弹窗 -->
    <view v-if="showFeedbackModal" class="feedback-modal-mask" @tap="closeFeedbackModal">
      <view class="feedback-modal" @tap.stop>
        <text class="feedback-modal-title">{{ feedbackModalRating === 'up' ? '👍 感谢反馈' : '👎 请告诉我们原因' }}</text>
        <textarea
          class="feedback-modal-input"
          v-model="feedbackModalReason"
          :placeholder="feedbackModalRating === 'up' ? '可选：补充说明...' : '请描述问题，帮助我们改进...'"
          :auto-height="true"
          :maxlength="500"
        />
        <view class="feedback-modal-btns">
          <text class="feedback-modal-cancel" @tap="closeFeedbackModal">取消</text>
          <text class="feedback-modal-submit" @tap="submitFeedback">提交</text>
        </view>
      </view>
    </view>

    <!-- 省市区选择器弹窗 -->
    <view v-if="showRegionPicker" class="region-picker-mask" @tap="showRegionPicker = false">
      <view class="region-picker" @tap.stop>
        <!-- 顶部：tab + 确定 -->
        <view class="rp-header">
          <view class="rp-tabs">
            <text :class="['rp-tab', 'active']">国内</text>
          </view>
          <text class="rp-confirm" @tap="confirmRegionPicker">确定</text>
        </view>
        <!-- 搜索框 -->
        <view class="rp-search">
          <text class="rp-search-icon">🔍</text>
          <input
            class="rp-search-input"
            v-model="regionSearchText"
            placeholder="搜索全国城市及地区"
            placeholder-class="rp-search-ph"
          />
        </view>
        <!-- 列标题（三列） -->
        <view class="rp-col-labels">
          <text class="rp-col-label">省份</text>
          <text class="rp-col-label">城市</text>
          <text class="rp-col-label">区县</text>
        </view>
        <!-- 三列滚动：省份 / 城市 / 区县 -->
        <view class="rp-columns">
          <scroll-view scroll-y :style="{ height: scrollHeight + 'px' }" class="rp-col">
            <text
              v-for="(p, pi) in filteredProvinces"
              :key="p.name"
              :class="['rp-item', regionSelProvince === p.name && 'active']"
              @tap="onSelectProvince(p.name)"
            >{{ p.name }}</text>
          </scroll-view>
          <scroll-view scroll-y :style="{ height: scrollHeight + 'px' }" class="rp-col">
            <text
              v-for="c in filteredCities"
              :key="c.name"
              :class="['rp-item', regionSelCity === c.name && 'active']"
              @tap="onSelectCity(c)"
            >{{ c.name }}</text>
          </scroll-view>
          <scroll-view scroll-y :style="{ height: scrollHeight + 'px' }" class="rp-col">
            <text
              v-for="d in filteredDistricts"
              :key="d.name"
              :class="['rp-item', regionSelDistrict === d.name && 'active']"
              @tap="regionSelDistrict = d.name"
            >{{ d.name }}</text>
          </scroll-view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
import { onLoad, onHide, onShow } from '@dcloudio/uni-app'
import { requireLogin } from '@/utils/authGuard'
import { useTheme } from '@/composables/useTheme'
import { chatWithXianzhiWS, closeAllWS } from '@/api/chat'
import {
  parsePillars, parseWuxing, parseDayun, parseShensha,
  downloadReport, getChart,
  fetchSessions, fetchMySessions, deleteSession as deleteSessionApi, getSessionMessages,
  getSessionBirthInfo,
  submitAnswerFeedback,
  transcribeAudio,
  type ChartData, type ChatSession,
} from '@/api'
import { getLocalDateString } from '@/utils/datetimePicker'
import { currentUserId, isLoggedIn, getToken, getUser, getBirthPlaceLocal, setBirthPlaceLocal, clearBirthPlaceLocal } from '@/utils/storage'
import { regionData, matchCityByName, type City } from '@/utils/region-data'

const { themeClass } = useTheme()

interface Message { role: 'user' | 'assistant'; content: string }
interface BirthInfo { time: string; gender: string }

const recording = ref(false)
const voiceBusy = ref(false)
const recorder = uni.getRecorderManager()
function audioAsDataUri(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => uni.getFileSystemManager().readFile({ filePath, encoding: 'base64', success: (res: any) => resolve(`data:audio/mpeg;base64,${res.data}`), fail: reject }))
}
async function toggleVoice() {
  if (thinking.value || voiceBusy.value) return
  if (recording.value) { recorder.stop(); return }
  recording.value = true
  recorder.start({ duration: 60000, sampleRate: 16000, numberOfChannels: 1, format: 'mp3' })
}
recorder.onStop(async (res) => {
  recording.value = false; voiceBusy.value = true
  try { const data = await transcribeAudio(await audioAsDataUri(res.tempFilePath), 'mp3'); inputText.value = inputText.value ? `${inputText.value}${data.text}` : data.text; uni.showToast({ title: '语音已转为文字', icon: 'none' }) }
  catch (e: any) { uni.showToast({ title: e?.message || '语音识别失败', icon: 'none' }) }
  finally { voiceBusy.value = false }
})
recorder.onError(() => { recording.value = false; voiceBusy.value = false; uni.showToast({ title: '录音不可用，请检查授权', icon: 'none' }) })

// 十二时辰 → HH:MM（用于把后端返回的"辰时"等标准化为 time picker 友好的格式）
const ZHI_HOUR_MAP: Record<string, string> = {
  '子': '00:00', '丑': '02:00', '寅': '04:00', '卯': '06:00',
  '辰': '08:00', '巳': '10:00', '午': '12:00', '未': '14:00',
  '申': '16:00', '酉': '18:00', '戌': '20:00', '亥': '22:00',
}
function zhiHourToHHMM(t?: string): string {
  if (!t) return ''
  // 已是 HH:MM 格式（如 "08:00"）
  if (/^\d{1,2}:\d{2}$/.test(t)) return t
  // 提取"辰时"中的"辰"
  const m = t.match(/([子丑寅卯辰巳午未申酉戌亥])/)
  if (m) return ZHI_HOUR_MAP[m[1]] || ''
  return t
}

const showBirth = ref(false)
const birthDate = ref('')
const birthTime = ref('')
const gender = ref<'男' | '女'>('男')
// 排盘引擎默认晚子时（子正换日，sect=2），不再提供用户手动切换
const sect = 2 as const
// 真太阳时：出生地与经度
const birthPlace = ref('')
const birthLongitude = ref(0)
/** 真太阳时修正量（分钟）。基准经度 120°E（北京时间），每度差 4 分钟 */
const solarTimeOffset = computed(() => {
  if (!birthLongitude.value || birthLongitude.value === 0) return 0
  return Math.round((120 - birthLongitude.value) * 4)
})

// ---- 省市区选择器弹窗状态 ----
const showRegionPicker = ref(false)
const regionSearchText = ref('')
const regionSelProvince = ref('')
const regionSelCity = ref('')
const regionSelDistrict = ref('')
const regionSelLongitude = ref(0)
/** scroll-view 固定高度（px），uni-app 要求具体数值才能滚动 */
const scrollHeight = ref(380)

// 搜索过滤
const filteredProvinces = computed(() => {
  if (!regionSearchText.value) return regionData
  const kw = regionSearchText.value.trim()
  return regionData.filter(p =>
    p.name.includes(kw) ||
    p.cities.some(c => c.name.includes(kw)) ||
    p.cities.some(c => c.districts.some(d => d.name.includes(kw)))
  )
})
const filteredCities = computed(() => {
  const prov = regionData.find(p => p.name === regionSelProvince.value)
  if (!prov) return []
  // 有搜索词时不过滤城市列表（避免搜省名后点省份城市列为空）
  return prov.cities
})
const filteredDistricts = computed(() => {
  const prov = regionData.find(p => p.name === regionSelProvince.value)
  if (!prov) return []
  const city = prov.cities.find(c => c.name === regionSelCity.value)
  if (!city) return []
  // 已选城市时直接展示全部区县（避免搜索词导致区县列为空）
  return city.districts
})

/** 搜索命中时自动定位到对应省市（用于搜区县名的情况） */
function autoLocateBySearch(kw: string) {
  for (const p of regionData) {
    for (const c of p.cities) {
      const match = c.districts.find(d => d.name.includes(kw))
      if (match) {
        regionSelProvince.value = p.name
        regionSelCity.value = c.name
        regionSelDistrict.value = match.name
        regionSelLongitude.value = c.longitude
        return true
      }
    }
  }
  // 搜城市名也自动定位
  for (const p of regionData) {
    const c = p.cities.find(city => city.name.includes(kw))
    if (c) {
      regionSelProvince.value = p.name
      regionSelCity.value = c.name
      regionSelLongitude.value = c.longitude
      if (c.districts.length > 0) regionSelDistrict.value = c.districts[0].name
      return true
    }
  }
  return false
}

function onSelectProvince(name: string) {
  regionSelProvince.value = name
  regionSelCity.value = ''
  regionSelDistrict.value = ''
  // 选省后清搜索词，避免城市列表被搜索词过度过滤
  regionSearchText.value = ''
}
function onSelectCity(c: City) {
  regionSelCity.value = c.name
  regionSelLongitude.value = c.longitude
  // 默认选第一个区县
  if (c.districts.length > 0 && !c.districts.some(d => d.name === regionSelDistrict.value)) {
    regionSelDistrict.value = c.districts[0].name
  }
  // 选城市后清搜索词，避免区县列表被搜索词过度过滤
  regionSearchText.value = ''
}
// 搜索词变化时自动定位到匹配的区县/城市（搜"浦北县"直接跳到广西钦州市浦北县）
watch(regionSearchText, (kw) => {
  const t = (kw || '').trim()
  if (!t) return
  autoLocateBySearch(t)
})
function confirmRegionPicker() {
  if (regionSelProvince.value && regionSelCity.value) {
    const parts = [regionSelProvince.value, regionSelCity.value]
    if (regionSelDistrict.value) parts.push(regionSelDistrict.value)
    birthPlace.value = parts.join(' ')
    birthLongitude.value = regionSelLongitude.value
    // 持久化出生地到本地，便于重新进入历史会话时恢复
    if (conversationId.value) setBirthPlaceLocal(conversationId.value, birthPlace.value, birthLongitude.value)
    // 已有出生时间则自动重排
    if (birthDate.value && birthTime.value && gender.value) {
      const time = `${birthDate.value} ${birthTime.value}`
      lastBirthInfo.value = { time, gender: gender.value }
      _skipNextChartWatch = true
      getChart(time, gender.value, sect, 1, birthLongitude.value).then(d => { chartData.value = d }).catch(() => { chartData.value = null })
    }
  }
  showRegionPicker.value = false
}
const inputText = ref('')
const thinking = ref(false)
const feedbackState = ref<Record<string, 'up' | 'down' | 'saved'>>({})
const feedbackReasons = ref<Record<string, string>>({})
const feedbackReasonOptions = ['分析具体', '结论符合', '事实有误', '太笼统', '风格不喜欢']
// 反馈弹窗状态
const showFeedbackModal = ref(false)
const feedbackModalMsg = ref<Message | null>(null)
const feedbackModalIndex = ref(-1)
const feedbackModalRating = ref<'up' | 'down'>('up')
const feedbackModalReason = ref('')
// 排盘与命理问答合并为同一条对话流：术语请教与排盘断事共用一份会话历史
const messages = ref<Message[]>([])
const scrollTop = ref(0)
const showScrollBottom = ref(false)
const SCROLL_BOTTOM_THRESHOLD = 200 // 距离底部超过此值(px)时显示按钮

function onMsgScroll(e: any) {
  const { scrollTop: st, scrollHeight, clientHeight } = e.detail
  // 距离底部的距离
  const distFromBottom = scrollHeight - st - clientHeight
  showScrollBottom.value = distFromBottom > SCROLL_BOTTOM_THRESHOLD
}
const lastBirthInfo = ref<BirthInfo | null>(null)
// 防止 watch 与显式 getChart 调用重复请求的标志
let _skipNextChartWatch = false
const showBaziModal = ref(false)
const chartData = ref<ChartData | null>(null)
// 会话ID：编码 user_id（mp-xianzhi__<userId>__<ts>），实现多用户会话隔离
function genConversationId(): string {
  const uid = currentUserId()
  return `mp-xianzhi__${uid || 'guest'}__${Date.now()}`
}
const conversationId = ref(genConversationId())

// 历史会话抽屉
const showHistoryDrawer = ref(false)
const historySessions = ref<ChatSession[]>([])
const historyLoading = ref(false)
const drawerWidth = ref(560)
let isResizing = false
let resizeStartX = 0
let resizeStartWidth = 0

function onResizeStart(e: any) {
  isResizing = true
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  resizeStartX = clientX
  resizeStartWidth = drawerWidth.value
}

function onResizeMove(e: any) {
  if (!isResizing) return
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const deltaX = clientX - resizeStartX
  let newWidth = resizeStartWidth + deltaX * 2
  newWidth = Math.max(400, Math.min(newWidth, uni.getSystemInfoSync().windowWidth * 1.8))
  drawerWidth.value = Math.round(newWidth)
}

function onResizeEnd() {
  isResizing = false
}

async function loadHistorySessions() {
  historyLoading.value = true
  try {
    // 登录后只显示自己的会话，避免多人共享后端时串号
    historySessions.value = isLoggedIn() ? await fetchMySessions() : await fetchSessions('xianzhi')
  } catch (e) {
    uni.showToast({ title: '加载历史失败', icon: 'none' })
    historySessions.value = []
  } finally {
    historyLoading.value = false
  }
}

function openHistoryDrawer() {
  showHistoryDrawer.value = true
  refreshProfile()
  loadHistorySessions()
}

function closeHistoryDrawer() {
  showHistoryDrawer.value = false
}

async function switchToSession(session: ChatSession) {
  if (!session?.id) return
  conversationId.value = session.id
  // 拉取该会话的历史消息
  try {
    const msgs = await getSessionMessages('xianzhi', session.id)
    messages.value = msgs.map(m => ({ role: m.role, content: m.content }))
    // 从后端恢复命盘上下文（支持农历/节日/时辰等自然语言输入场景）
    lastBirthInfo.value = null
    chartData.value = null
    birthDate.value = ''
    birthTime.value = ''
    gender.value = '男' as '男' | '女'
    // 先清空出生地/经度，避免上一个会话/命盘的值跨会话挂载到本会话
    // （下面只在本地有存档时才恢复，无档必须显式清空，否则会沿用陈旧值）
    birthPlace.value = ''
    birthLongitude.value = 0
    const bi = await getSessionBirthInfo(session.id)
    if (bi.time && bi.gender) {
      lastBirthInfo.value = { time: bi.time, gender: bi.gender }
      const [d, t] = bi.time.split(' ')
      birthDate.value = d || ''
      // 时辰（如"辰时"）映射为 HH:MM，确保 time picker 能正常显示
      birthTime.value = zhiHourToHHMM(t)
      gender.value = bi.gender as '男' | '女'
      _skipNextChartWatch = true
      try { chartData.value = await getChart(bi.time, bi.gender, 2, 1) } catch { chartData.value = null }
    }
    // 从本地存储恢复出生地/经度（后端 birth-info 接口不含这两项）
    const bp = getBirthPlaceLocal(session.id)
    if (bp) {
      birthPlace.value = bp.place
      birthLongitude.value = bp.longitude
    }
  } catch (e) {
    uni.showToast({ title: '加载消息失败', icon: 'none' })
  }
  feedbackState.value = {}
  feedbackReasons.value = {}
  closeHistoryDrawer()
  // 延迟滚到底部：等抽屉关闭动画 + 消息列表渲染完毕
  setTimeout(() => scrollToBottom(), 350)
}

async function deleteHistorySession(id: string) {
  uni.showModal({
    title: '删除会话',
    content: '确定删除该会话的所有记录吗？',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await deleteSessionApi('xianzhi', id)
        // 如果删除的是当前会话，新建一个
        if (id === conversationId.value) {
          newSession()
        }
        await loadHistorySessions()
      } catch (e) {
        uni.showToast({ title: '删除失败', icon: 'none' })
      }
    },
  })
}

function formatSessionTime(t: string): string {
  if (!t) return ''
  // 后端返回形如 "2026-07-14 12:34:56+08:00"，截取到分钟
  return t.replace('T', ' ').slice(0, 16)
}

// 状态栏高度（自定义导航栏需要）
const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getWindowInfo()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

// 键盘高度：键盘弹起时让输入栏固定在键盘上方，同时给消息区留出底部空间
const keyboardHeight = ref(0)
const INPUT_BAR_BASE_RPX = 128 // 输入栏基础高度（含上下 padding），与样式保持一致
const inputBarStyle = computed(() => {
  // 输入栏 fixed 在视口底部，键盘弹起时抬高 bottom
  const bottom = keyboardHeight.value > 0 ? keyboardHeight.value : 0
  return `bottom: ${bottom}px;`
})
const messagesStyle = computed(() => {
  const kb = keyboardHeight.value > 0 ? keyboardHeight.value : 0
  return `padding-bottom: calc(${INPUT_BAR_BASE_RPX}rpx + ${kb}px + env(safe-area-inset-bottom));`
})
let _kbHandler: ((res: any) => void) | null = null
let _visualViewportHandler: (() => void) | null = null
onMounted(() => {
  // #ifdef MP-WEIXIN
  _kbHandler = (res: any) => {
    keyboardHeight.value = res?.height || 0
    if (keyboardHeight.value > 0) setTimeout(scrollToBottom, 150)
  }
  uni.onKeyboardHeightChange(_kbHandler)
  // #endif

  // #ifdef H5
  if (typeof window !== 'undefined' && (window as any).visualViewport) {
    const vv = (window as any).visualViewport
    const updateH5KeyboardHeight = () => {
      const h = Math.max(0, window.innerHeight - vv.height)
      keyboardHeight.value = h
      if (h > 0) setTimeout(scrollToBottom, 150)
    }
    _visualViewportHandler = updateH5KeyboardHeight
    vv.addEventListener('resize', updateH5KeyboardHeight)
  }
  // #endif

  // #ifdef H5
  if (typeof window !== 'undefined') {
    window.addEventListener('mousemove', onResizeMove)
    window.addEventListener('mouseup', onResizeEnd)
  }
  // #endif
})
onBeforeUnmount(() => {
  // #ifdef MP-WEIXIN
  if (_kbHandler) uni.offKeyboardHeightChange(_kbHandler)
  // #endif
  // #ifdef H5
  if (_visualViewportHandler && typeof window !== 'undefined' && (window as any).visualViewport) {
    (window as any).visualViewport.removeEventListener('resize', _visualViewportHandler)
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('mousemove', onResizeMove)
    window.removeEventListener('mouseup', onResizeEnd)
  }
  // #endif
})

const today = getLocalDateString()
const birthTimeFull = computed(() =>
  birthDate.value && birthTime.value ? `${birthDate.value} ${birthTime.value}` : ''
)
const birthSummary = computed(() =>
  birthTimeFull.value ? `${birthTimeFull.value} ${gender.value}${birthPlace.value ? ' · ' + birthPlace.value : ''}` : '点击设置出生信息'
)

const placeholderText = '请输入你的问题…'

// 抽屉用户区：头像与昵称（取自登录态）
// 用 ref 而非 computed(getUser())，因为 uni.getStorageSync 不被 Vue 响应追踪，
// computed 会永久缓存首次求值结果导致登录后仍显示"未登录"
const profileUser = ref<any>(null)
const nickname = computed(() => profileUser.value?.nickname || (isLoggedIn() ? '我的' : '未登录'))
const avatarText = computed(() => {
  const n = profileUser.value?.nickname
  return n ? n.charAt(0) : (isLoggedIn() ? '我' : '易')
})
/** 从 storage 刷新登录态（打开抽屉 / 页面 onShow 时调用） */
function refreshProfile() {
  profileUser.value = getUser()
}

// 出生信息面板手动修改时，自动重拉 chartData
watch([birthDate, birthTime, gender, birthLongitude], async ([d, t, g]) => {
  // 显式调用 getChart 的地方（applyBirth/onChartContext/switchToSession/tryExtractBirth）
  // 已自行处理 chartData，跳过 watch 避免重复请求
  if (_skipNextChartWatch) { _skipNextChartWatch = false; return }
  if (d && t && g) {
    const time = `${d} ${t}`
    lastBirthInfo.value = { time, gender: g }
    try { chartData.value = await getChart(time, g, 2, 1, birthLongitude.value || undefined) } catch { chartData.value = null }
  }
})

/** 预填出生信息并自动发起排盘（来自命例/档案带入） */
async function applyBirth(bt: string, g: '男' | '女', name?: string) {
  // 外部带入的是一张新命盘，先清空出生地/经度，避免沿用上一个命盘的地点
  birthPlace.value = ''
  birthLongitude.value = 0
  const [d, t] = bt.split(' ')
  birthDate.value = d || ''
  birthTime.value = zhiHourToHHMM(t)
  gender.value = g
  lastBirthInfo.value = { time: bt, gender: g }
  _skipNextChartWatch = true
  try { chartData.value = await getChart(bt, g, 2, 1) } catch { chartData.value = null }
  const autoMsg = name
    ? `${g}，${bt}，排盘并分析（来自：${name}）`
    : `${g}，${bt}，排盘并分析整体命盘`
  inputText.value = autoMsg
  onSend()
}

// 接收命例页跳转参数，自动预填并排盘
onLoad(async (query) => {
  if (query?.birthTime && query?.gender) {
    await applyBirth(query.birthTime as string, query.gender as '男' | '女', query.name as string | undefined)
  }
})

// 从「我的」页带入对话 / 继续会话：通过本地存储传递参数（tabBar 页无法用 navigateTo 传参）
onShow(() => {
  if (!requireLogin()) return
  const lp = uni.getStorageSync('XZ_LAUNCH')
  if (!lp) return
  uni.removeStorageSync('XZ_LAUNCH')
  if (lp.conversationId) {
    switchToSession({ id: lp.conversationId } as ChatSession)
  } else if (lp.birthTime && lp.gender) {
    newSession()
    applyBirth(lp.birthTime, lp.gender, lp.name)
  }
})

// 切走 tab / 页面隐藏时关闭 WS，避免 socket 累积超过小程序 5 个上限
onHide(() => { closeAllWS() })

function onDateChange(e: any) { birthDate.value = e.detail.value }
function onTimeChange(e: any) { birthTime.value = e.detail.value }
function goDisclaimer() { uni.navigateTo({ url: '/pages/legal/disclaimer' }) }
function goSettings() { uni.navigateTo({ url: '/pages/settings/index' }) }
function goTarot() { uni.navigateTo({ url: '/pages/tarot/index' }) }
function goLiuYao() { uni.navigateTo({ url: '/pages/liuyao/index' }) }
function goHuangLi() { uni.navigateTo({ url: '/pages/huangli/index' }) }
function goMine() {
  uni.navigateTo({ url: isLoggedIn() ? '/pages/mine/index' : '/pages/login/index' })
}

/** 跳转合婚页面 */
function goHehun() {
  uni.navigateTo({ url: '/pages/hehun/index' })
}

/** 新建会话：生成新会话ID并清空命盘上下文 */
function newSession() {
  conversationId.value = genConversationId()
  messages.value.splice(0, messages.value.length)
  inputText.value = ''
  lastBirthInfo.value = null
  chartData.value = null
  birthDate.value = ''
  birthTime.value = ''
  birthPlace.value = ''
  birthLongitude.value = 0
  feedbackState.value = {}
  feedbackReasons.value = {}
}

/** 从 ReAct 输出中提取 [回答] 部分（用于解析可视化数据） */
function extractAnswer(text: string): string {
  if (!text) return ''
  const m = text.match(/\[回答\]\s*([\s\S]*)/)
  return m ? m[1] : text
}

/** 判断是否还在思考（含 ReAct 标记） */
function isThinking(content: string) {
  return typeof content === 'string' && (content.includes('[思考]') || content.includes('[行动]') || content.includes('[观察]'))
}

/** 生成消息反馈的唯一 key */
const msgFeedbackKey = (msg: Message, index: number) =>
  `${conversationId.value}:${index}:${msg.content.slice(0, 64)}`

/** 获取指定消息之前的最后一条用户消息 */
function questionBefore(index: number): string {
  for (let i = index - 1; i >= 0; i--) {
    if (messages.value[i]?.role === 'user') return messages.value[i].content
  }
  return ''
}

/** 打开反馈弹窗 */
function openFeedbackModal(msg: Message, index: number, rating: 'up' | 'down') {
  feedbackModalMsg.value = msg
  feedbackModalIndex.value = index
  feedbackModalRating.value = rating
  feedbackModalReason.value = feedbackReasons.value[msgFeedbackKey(msg, index)] || ''
  showFeedbackModal.value = true
}

/** 关闭反馈弹窗 */
function closeFeedbackModal() {
  showFeedbackModal.value = false
  feedbackModalMsg.value = null
  feedbackModalIndex.value = -1
  feedbackModalReason.value = ''
}

/** 提交反馈（弹窗确认后） */
async function submitFeedback() {
  const msg = feedbackModalMsg.value
  const index = feedbackModalIndex.value
  const rating = feedbackModalRating.value
  if (!msg || index < 0) return
  const key = msgFeedbackKey(msg, index)
  const reason = feedbackModalReason.value.trim() || (rating === 'up' ? '有帮助' : '不太准')
  feedbackReasons.value[key] = reason
  feedbackState.value[key] = rating
  showFeedbackModal.value = false
  try {
    await submitAnswerFeedback({
      conversation_id: conversationId.value,
      question: questionBefore(index),
      answer: msg.content,
      rating,
      reason,
      chart_snapshot: chartData.value && lastBirthInfo.value
        ? {
            chartData: chartData.value,
            birthInfo: lastBirthInfo.value,
            birth_time: lastBirthInfo.value.time,
            gender: lastBirthInfo.value.gender,
          }
        : lastBirthInfo.value
          ? { birth_time: lastBirthInfo.value.time, gender: lastBirthInfo.value.gender }
          : {},
    })
    feedbackState.value[key] = 'saved'
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
    delete feedbackState.value[key]
    delete feedbackReasons.value[key]
  }
}

/** 格式化显示内容：处理 ReAct 标记 */
function formatContent(text: string): string {
  if (!text) return ''
  return text
    .replace(/\[思考\]\s*/g, '【思考】 ')
    .replace(/\[行动\]\s*/g, '【行动】 ')
    .replace(/\[观察\]\s*/g, '【观察】 ')
    .replace(/\[回答\]\s*/g, '')
    .replace(/\[结束\].*/g, '')
}

function scrollToBottom() {
  showScrollBottom.value = false
  nextTick(() => {
    scrollTop.value = scrollTop.value === 99998 ? 99999 : 99998
  })
}

function onInputFocus() {
  // 聚焦时延迟滚动到底部，避免键盘弹起过程中消息被遮挡
  setTimeout(scrollToBottom, 200)
  setTimeout(scrollToBottom, 400)
}

/** 最后一条助手消息（用于解析命盘数据给 modal） */
const lastAssistantContent = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === 'assistant') return messages.value[i].content
  }
  return ''
})
const modalPillars = computed(() => chartData.value?.pillars?.length ? chartData.value.pillars : parsePillars(extractAnswer(lastAssistantContent.value)))
const modalWuxing = computed(() => chartData.value?.wuxing?.length ? chartData.value.wuxing : parseWuxing(extractAnswer(lastAssistantContent.value)))
const modalDayun = computed(() => chartData.value?.dayun?.length ? chartData.value.dayun : parseDayun(extractAnswer(lastAssistantContent.value)))
const modalShensha = computed(() => chartData.value?.shensha?.length ? chartData.value.shensha : parseShensha(extractAnswer(lastAssistantContent.value)))

function openBaziModal() {
  if (!modalPillars.value.length && !modalWuxing.value.length) {
    uni.showToast({ title: '暂无可显示的命盘', icon: 'none' })
    return
  }
  showBaziModal.value = true
}

/** 从用户消息中提取出生信息，同步更新顶部表单（watch 会自动拉取 chartData 并设置 lastBirthInfo） */
async function tryExtractBirth(text: string) {
  const m = text.match(/(男|女)/)
  const t = text.match(/(\d{4}[-年/]\d{1,2}[-月/]\d{1,2}[日 ]+\d{1,2}[:：]\d{1,2})/)
  if (m && t) {
    const time = t[1].replace(/年|月/g, '-').replace('日', '').replace('：', ':').trim()
    // 同步设置 lastBirthInfo + 表单字段，确保按钮立即显示
    lastBirthInfo.value = { time, gender: m[1] as '男' | '女' }
    const [d, tm] = time.split(' ')
    birthDate.value = d || ''
    birthTime.value = zhiHourToHHMM(tm)
    gender.value = m[1] as '男' | '女'
    // 主动拉取 chartData（对齐 web 端 tryExtractBirth + fetchChartData 行为）
    _skipNextChartWatch = true
    try { chartData.value = await getChart(time, m[1] as '男' | '女', 2, 1) } catch { chartData.value = null }
  }
}

function downloadPdfReport() {
  if (!birthTimeFull.value && !lastBirthInfo.value) {
    uni.showToast({ title: '请先设置出生信息', icon: 'none' })
    return
  }
  const time = birthTimeFull.value || lastBirthInfo.value?.time
  const g = gender.value || lastBirthInfo.value?.gender
  if (time && g) downloadReport(time, g)
}

function onSend() {
  const text = inputText.value.trim()
  if (!text || thinking.value) return
  const targetList = messages.value
  targetList.push({ role: 'user', content: text })
  inputText.value = ''
  tryExtractBirth(text)
  thinking.value = true
  scrollToBottom()

  const assistantMsg: Message = { role: 'assistant', content: '' }
  targetList.push(assistantMsg)
  const idx = targetList.length - 1

  const onMessage = (chunk: string) => {
    targetList[idx].content += chunk
    scrollToBottom()
  }
  const onDone = () => { thinking.value = false }
  const onError = (err: string) => {
    thinking.value = false
    // 纯连接类异常（WS 断开/超时/域名未配置）走 toast 提示，不污染对话历史
    const isConnErr = /连接|超时|域名|网络|WebSocket|WS|Socket/i.test(err)
    if (isConnErr) {
      uni.showToast({ title: err, icon: 'none', duration: 2500 })
      // 移除刚压入的占位 assistant 消息，保留用户问题以便重发
      targetList.splice(idx, 1)
      nextTick(scrollToBottom)
      return
    }
    // 业务错误（如 LLM 限流、解析失败等）保留在消息流，便于用户回看
    targetList[idx].content = targetList[idx].content || `[出错] ${err}`
  }
  // 后端从 LLM 工具调用中提取到出生信息时回调（覆盖自然语言输入场景）
  const onChartContext = async (bt: string, g: string, bp?: string) => {
    if (!bt || !g) return
    // 记录切换前的八字，用于区分"同一命盘的追问"与"换了一张新命盘"
    const prevTime = birthTimeFull.value
    const [d, t] = bt.split(' ')
    birthDate.value = d || ''
    birthTime.value = zhiHourToHHMM(t)
    gender.value = g as '男' | '女'
    lastBirthInfo.value = { time: bt, gender: g as '男' | '女' }
    // 出生地必须跟随"当前这张命盘"走，否则会跨命盘串值：
    //  - 本次后端提取到出生地 → 采用（覆盖上一张命盘遗留的值；库未收录也用原文替换，经度置 0 为安全默认）；
    //  - 本次未提到出生地且八字已变（新命盘 / 换人）→ 清空，不让上一个地点的真太阳时挂到这张命盘；
    //  - 八字未变（同一命盘的追问）且已有手动选择的地点 → 保留手动精度，不覆盖。
    const isNewChart = bt !== prevTime
    if (bp) {
      if (isNewChart || !birthPlace.value) {
        const matched = matchCityByName(bp)
        if (matched) {
          birthPlace.value = `${matched.province} ${matched.city}`
          birthLongitude.value = matched.longitude
        } else {
          birthPlace.value = bp
          birthLongitude.value = 0
        }
        if (conversationId.value) setBirthPlaceLocal(conversationId.value, birthPlace.value, birthLongitude.value)
      }
    } else if (isNewChart) {
      birthPlace.value = ''
      birthLongitude.value = 0
      if (conversationId.value) clearBirthPlaceLocal(conversationId.value)
    }
    // 主动拉取结构化命盘数据（命盘详情弹窗内容）
    _skipNextChartWatch = true
    try {
      chartData.value = await getChart(bt, g, 2, 1, birthLongitude.value || undefined)
    } catch {
      chartData.value = null
    }
  }

  chatWithXianzhiWS(text, {
    conversationId: conversationId.value,
    birthTime: birthTimeFull.value || undefined,
    gender: gender.value,
    birthPlace: birthPlace.value || undefined,
    sect,
    token: getToken(),
    onMessage, onDone, onError, onChartContext,
  })
}

// 初始欢迎语
messages.value.push({
  role: 'assistant',
  content: '您好，我是先知。可直接请教命理问题，也可报上生辰、性别和出生地，我会帮你分析命盘。',
})
</script>

<style lang="scss">
/* === 先知 · 白底黑字水墨风 + 太极图背景 === */
.page {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  box-sizing: border-box;
  overflow-x: hidden;
  background: $color-bg;
  color: $color-ink;
}

/* === 水墨山水背景 === */
.landscape {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

/* 山的通用样式 */
.mountain {
  position: absolute;
  left: 0;
  right: 0;
  pointer-events: none;
}

/* 远山 - 最浅、最低起伏 */
.mountain-far {
  bottom: 0;
  height: 45%;
  background: linear-gradient(to top,
    var(--x-mountain-far) 0%,
    transparent 100%);
  clip-path: polygon(
    0% 100%,
    0% 75%, 8% 68%, 15% 72%, 22% 60%, 30% 65%, 38% 55%, 45% 62%, 52% 50%, 60% 58%, 68% 52%, 75% 60%, 82% 55%, 90% 62%, 100% 58%,
    100% 100%
  );
}

/* 中山 - 中等深度 */
.mountain-mid {
  bottom: 0;
  height: 38%;
  background: linear-gradient(to top,
    var(--x-mountain-mid) 0%,
    transparent 100%);
  clip-path: polygon(
    0% 100%,
    0% 70%, 6% 60%, 14% 68%, 20% 55%, 28% 62%, 35% 50%, 42% 58%, 50% 45%, 58% 55%, 65% 48%, 72% 58%, 80% 52%, 88% 60%, 95% 55%, 100% 62%,
    100% 100%
  );
}

/* 山间云雾 */
.mountain-mist {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 28%;
  height: 12%;
  background: linear-gradient(to bottom,
    var(--x-mist) 0%,
    transparent 100%);
  pointer-events: none;
  z-index: 1;
}

/* 近山 - 最深、最高 */
.mountain-near {
  bottom: 0;
  height: 32%;
  background: linear-gradient(to top,
    var(--x-mountain-near) 0%,
    transparent 100%);
  clip-path: polygon(
    0% 100%,
    0% 65%, 10% 50%, 18% 58%, 28% 42%, 38% 52%, 48% 38%, 56% 48%, 66% 40%, 74% 52%, 84% 45%, 92% 55%, 100% 48%,
    100% 100%
  );
}

/* 飞鸟 - V 形 */
.bird {
  position: absolute;
  width: 28rpx;
  height: 16rpx;
  pointer-events: none;
  z-index: 2;
}
.bird::before,
.bird::after {
  content: '';
  position: absolute;
  top: 0;
  width: 14rpx;
  height: 14rpx;
  border: 2rpx solid var(--x-bird);
  border-bottom: none;
  border-right: none;
  border-radius: 50% 0 0 0;
}
.bird::before { left: 0; transform: rotate(45deg); }
.bird::after { right: 0; transform: rotate(135deg) scaleX(-1); transform-origin: top right; }

.bird-1 {
  top: 22%;
  left: 20%;
  animation: birdDrift 18s ease-in-out infinite;
}
.bird-2 {
  top: 18%;
  left: 55%;
  transform: scale(0.8);
  opacity: 0.7;
  animation: birdDrift 20s ease-in-out infinite -6s;
}
.bird-3 {
  top: 28%;
  right: 18%;
  transform: scale(0.9);
  opacity: 0.5;
  animation: birdDrift 22s ease-in-out infinite -12s;
}
@keyframes birdDrift {
  0% { transform: translate(0, 0) scale(var(--s, 1)); }
  50% { transform: translate(40rpx, -20rpx) scale(var(--s, 1)); }
  100% { transform: translate(0, 0) scale(var(--s, 1)); }
}

/* 落款印章 */
.seal {
  position: absolute;
  bottom: 10%;
  right: 6%;
  width: 56rpx;
  height: 56rpx;
  line-height: 52rpx;
  text-align: center;
  background: $color-vermilion;
  color: $color-bg;
  font-size: 32rpx;
  font-weight: 600;
  font-family: $font-family-display;
  border: 2rpx solid $color-vermilion;
  box-shadow: 0 0 12rpx rgba(184, 72, 60, 0.25);
  opacity: 0.78;
  transform: rotate(-3deg);
  pointer-events: none;
  z-index: 2;
}

/* 状态栏占位 */
.status-bar {
  background: $color-bg;
  width: 100%;
  position: relative;
  z-index: 1;
}

/* === 顶部标题头 === */
.header {
  width: 100%;
  box-sizing: border-box;
  background: $color-bg;
  border-bottom: 1rpx solid $color-border;
  padding: 16rpx 32rpx 20rpx;
  overflow: hidden;
  position: relative;
  z-index: 1;
}
.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 8rpx;
}
.header-title {
  font-size: 40rpx;
  font-weight: 600;
  color: $color-primary;
  letter-spacing: 0.12em;
}
.icon-btn {
  width: 64rpx;
  height: 64rpx;
  line-height: 60rpx;
  text-align: center;
  color: $color-ink-light;
  font-size: 36rpx;
}
.bazi-btn {
  color: $color-primary;
  font-size: 40rpx;
}

/* === 出生信息面板 === */
.birth-panel {
  background: $color-bg-card;
  border-bottom: 1rpx solid $color-border;
  position: relative;
  z-index: 1;
}
.birth-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 32rpx;
}
.birth-bar-left {
  display: flex;
  align-items: center;
  gap: 16rpx;
}
.birth-icon {
  color: $color-vermilion;
  font-size: 28rpx;
}
.birth-summary {
  color: $color-ink;
  font-size: 30rpx;
  letter-spacing: 0.05em;
}
.arrow {
  color: $color-ink-lighter;
  font-size: 22rpx;
}
.birth-form {
  padding: 16rpx 32rpx 28rpx;
}
.form-row {
  display: flex;
  align-items: center;
  margin-bottom: 20rpx;
  gap: 16rpx;
}
.label {
  width: 140rpx;
  font-size: 28rpx;
  color: $color-ink-lighter;
}
.picker {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20rpx 24rpx;
  background: $color-bg-warm;
  border-radius: 20rpx;
  border: 1rpx solid $color-border;
}
.picker-text {
  font-size: 30rpx;
  color: $color-ink;
}
.picker-icon {
  color: $color-ink-lighter;
  font-size: 30rpx;
}
.seg-group {
  flex: 1;
  display: flex;
  border: 1rpx solid $color-border;
  border-radius: 20rpx;
  overflow: hidden;
}
.seg {
  flex: 1;
  text-align: center;
  padding: 18rpx 0;
  font-size: 30rpx;
  color: $color-ink-light;
  background: $color-bg-warm;
}
.seg.active {
  background: rgba(44, 44, 44, 0.08);
  color: $color-primary;
}
.legal-link {
  font-size: 26rpx;
  color: $color-ink-light;
  margin-top: 8rpx;
}
.sect-hint {
  font-size: 24rpx;
  color: $color-ink-light;
  text-align: center;
  padding: 8rpx 0 4rpx;
  line-height: 1.5;
}
.place-picker { cursor: pointer; }
.solar-hint {
  display: block;
  font-size: 24rpx;
  color: $color-primary;
  margin-top: 6rpx;
  padding-left: 156rpx;
}

/* === 消息列表 === */
.messages {
  flex: 1;
  padding: 24rpx 24rpx calc(24rpx + 128rpx + env(safe-area-inset-bottom));
  overflow-x: hidden;
  width: 100%;
  box-sizing: border-box;
  position: relative;
  z-index: 1;
}
.messages::-webkit-scrollbar { width: 10px; }
.messages::-webkit-scrollbar-track { background: rgba(255,255,255,0.03); border-radius: 5px; }
.messages::-webkit-scrollbar-thumb { background: rgba(212,175,55,0.25); border-radius: 5px; border: 2px solid transparent; background-clip: padding-box; min-height: 60px; }
.messages::-webkit-scrollbar-thumb:hover { background: rgba(212,175,55,0.5); border: 2px solid transparent; background-clip: padding-box; }

/* 回到底部悬浮按钮 */
.scroll-bottom-btn {
  position: absolute;
  right: 24rpx;
  bottom: 180rpx;
  width: 72rpx;
  height: 72rpx;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 4rpx 20rpx rgba(0,0,0,0.12);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  animation: fadeInUp 0.2s ease-out;
}
.scroll-bottom-icon {
  font-size: 36rpx;
  color: #666;
  font-weight: 600;
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(16rpx); }
  to   { opacity: 1; transform: translateY(0); }
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60rpx 0;
}
.empty-avatar {
  width: 128rpx;
  height: 128rpx;
  line-height: 128rpx;
  text-align: center;
  background: $color-primary;
  color: $color-bg;
  border-radius: 50%;
  font-size: 56rpx;
  font-weight: 600;
  margin-bottom: 24rpx;
  border: 1rpx solid $color-primary;
}
.empty-title {
  font-size: 38rpx;
  font-weight: 600;
  color: $color-ink;
  margin-bottom: 12rpx;
  letter-spacing: 0.05em;
}
.empty-desc {
  font-size: 28rpx;
  color: $color-ink-lighter;
}

/* === 消息项 === */
.msg {
  display: flex;
  margin-bottom: 32rpx;
  gap: 16rpx;
  align-items: flex-start;
  padding: 0;
  width: 100%;
  box-sizing: border-box;
}
.msg.user {
  flex-direction: row-reverse;
}
.avatar {
  flex-shrink: 0;
  width: 72rpx;
  height: 72rpx;
  line-height: 72rpx;
  text-align: center;
  background: $color-primary;
  color: $color-bg;
  border-radius: 50%;
  font-size: 26rpx;
  font-weight: 600;
  border: 1rpx solid $color-primary;
}
.msg.user .avatar {
  background: $color-vermilion;
  border-color: $color-vermilion;
}
.msg-body {
  flex: 1;
  min-width: 0;
  max-width: calc(100% - 88rpx);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  overflow-x: hidden;
  box-sizing: border-box;
}
.msg.user .msg-body {
  align-items: flex-end;
  margin-left: auto;
}
.msg-text {
  width: auto;
  max-width: 88%;
  padding: 22rpx 32rpx;
  border-radius: 8rpx 28rpx 28rpx 28rpx;
  font-size: 32rpx;
  line-height: 1.6;
  word-break: break-word;
  overflow-wrap: break-word;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  color: $color-ink;
  box-sizing: border-box;
  overflow: hidden;
  box-shadow: 0 2rpx 6rpx rgba(0, 0, 0, 0.04);
  /* 深色字压白底：灰度抗锯齿让笔画边缘更锐利，避免发虚 */
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
/* 统一助手 rich-text 与用户气泡字号：MarkdownRender 默认 28rpx，这里让气泡正文统一为 32rpx */
.msg-text :deep(.md-render) {
  font-size: 32rpx;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
/* 标题层级始终大于正文 32rpx，避免 h3/h4 小于正文显得错乱 */
.msg-text :deep(.md-render) .md-h1,
.msg-text :deep(.md-render) .md-h2 { font-size: 38rpx; }
.msg-text :deep(.md-render) .md-h3 { font-size: 34rpx; }
.msg-text :deep(.md-render) .md-h4 { font-size: 32rpx; }
.msg.user .msg-text {
  /* 多行文字从左开始排列（与 AI 消息一致），气泡仍右贴齐 */
  text-align: left;
  background: $color-primary;
  border-radius: 28rpx 8rpx 28rpx 28rpx;
  color: $color-bg;
  border: none;
  /* 浅色字压深底：改回亚像素抗锯齿，避免文字被磨得过细 */
  -webkit-font-smoothing: auto;
}
.msg-text.thinking { opacity: 0.7; }
.typing { color: $color-ink-light; }

/* === 回答反馈栏 === */
.feedback-bar {
  margin-top: 12rpx;
  display: flex;
  align-items: center;
  gap: 12rpx;
  flex-wrap: wrap;
}
.feedback-chip {
  width: 48rpx;
  height: 48rpx;
  line-height: 48rpx;
  text-align: center;
  font-size: 28rpx;
  color: $color-ink-light;
  background: rgba(44, 44, 44, 0.04);
  border: 1rpx solid $color-border;
  border-radius: 50%;
  transition: all 0.2s;
  &.active-up {
    color: #fff;
    background: #4caf50;
    border-color: #4caf50;
  }
  &.active-down {
    color: #fff;
    background: #f44336;
    border-color: #f44336;
  }
}
.feedback-saved {
  font-size: 22rpx;
  color: $color-ink-lighter;
}

/* === 反馈弹窗 === */
.feedback-modal-mask {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.feedback-modal {
  width: 600rpx;
  background: #fff;
  border-radius: 24rpx;
  padding: 40rpx 32rpx 32rpx;
  display: flex;
  flex-direction: column;
  gap: 24rpx;
}
.feedback-modal-title {
  font-size: 30rpx;
  font-weight: 600;
  color: $color-primary;
  text-align: center;
}
.feedback-modal-input {
  width: 100%;
  min-height: 120rpx;
  padding: 20rpx 24rpx;
  font-size: 26rpx;
  color: $color-ink;
  background: $color-bg-warm;
  border: 1rpx solid $color-border;
  border-radius: 16rpx;
  box-sizing: border-box;
}
.feedback-modal-btns {
  display: flex;
  gap: 20rpx;
  justify-content: flex-end;
}
.feedback-modal-cancel {
  padding: 16rpx 40rpx;
  font-size: 26rpx;
  color: $color-ink-light;
  background: $color-bg-warm;
  border: 1rpx solid $color-border;
  border-radius: 20rpx;
}
.feedback-modal-submit {
  padding: 16rpx 40rpx;
  font-size: 26rpx;
  color: #fff;
  background: $color-primary;
  border-radius: 20rpx;
}

/* === 输入栏 === */
.input-bar {
  display: flex;
  align-items: flex-end;
  padding: 16rpx 32rpx calc(16rpx + env(safe-area-inset-bottom));
  background: $color-bg-card;
  border-top: 1rpx solid $color-border;
  gap: 16rpx;
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 100;
  transition: bottom 0.15s ease;
}
.input-wrap {
  flex: 1;
  background: $color-bg-warm;
  border-radius: 32rpx;
  border: 1rpx solid $color-border;
  padding: 8rpx 28rpx;
}
.input {
  width: 100%;
  min-height: 64rpx;
  max-height: 200rpx;
  padding: 14rpx 0;
  font-size: 32rpx;
  color: $color-ink;
}
.input-placeholder {
  color: $color-ink-lighter;
}
.send-btn {
  flex-shrink: 0;
  width: 72rpx;
  height: 72rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 与输入框水平对齐（input-bar 为 flex-end，这里单独让按钮垂直居中） */
  align-self: center;
  background: #fff;
  border-radius: 50%;
  transition: all 0.2s ease;
}
.send-btn:active:not(.disabled) {
  transform: scale(0.92);
  background: #f0f0f0;
}
.send-btn.disabled {
  opacity: 0.3;
  pointer-events: none;
}
.voice-btn {
  flex-shrink: 0;
  width: 72rpx;
  height: 72rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 与输入框水平对齐（input-bar 为 flex-end，这里单独让按钮垂直居中） */
  align-self: center;
  transition: all 0.2s ease;
}
.voice-btn:active:not(.disabled) {
  transform: scale(0.9);
}
.voice-btn.disabled {
  opacity: 0.3;
  pointer-events: none;
}
.voice-text {
  font-size: 48rpx;
  line-height: 1;
  opacity: 0.7;
}
.recording-pulse {
  color: #ff4757;
  font-size: 28rpx;
  animation: voicePulse 1s ease-in-out infinite;
}
.busy-bounce {
  font-size: 32rpx;
  animation: voiceBounce 0.8s ease-in-out infinite;
}
@keyframes voicePulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.85); }
}
@keyframes voiceBounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4rpx); }
}
.send-icon {
  display: inline-block;
  color: #333;
  font-size: 52rpx;
  line-height: 1;
  font-weight: 500;
  transform: scale(1.2);
}

/* ============ 历史会话抽屉 ============ */
.drawer-mask {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 1000;
}
.drawer-panel {
  position: fixed;
  top: 0; left: 0; bottom: 0;
  background: $color-bg-warm;
  display: flex;
  flex-direction: column;
  overflow: hidden; /* 关键：约束子元素，否则 scroll-view 拿不到确定高度、无法滚动 */
  z-index: 1001;
  box-shadow: 4rpx 0 24rpx rgba(0, 0, 0, 0.15);
  transition: width .15s ease-out;
}
.drawer-resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 24rpx;
  cursor: ew-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  touch-action: none;
}
.resize-indicator {
  width: 6rpx;
  height: 80rpx;
  background: linear-gradient(180deg,
    transparent 0%,
    rgba(212, 175, 55, 0.3) 20%,
    rgba(212, 175, 55, 0.6) 50%,
    rgba(212, 175, 55, 0.3) 80%,
    transparent 100%
  );
  border-radius: 3rpx;
  transition: all .2s ease;
}
.drawer-resize-handle:hover .resize-indicator,
.drawer-resize-handle:active .resize-indicator {
  background: linear-gradient(180deg,
    transparent 0%,
    rgba(212, 175, 55, 0.5) 20%,
    rgba(212, 175, 55, 0.9) 50%,
    rgba(212, 175, 55, 0.5) 80%,
    transparent 100%
  );
  width: 8rpx;
  height: 120rpx;
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 30rpx 32rpx 20rpx;
  border-bottom: 1rpx solid rgba(44, 44, 44, 0.1);
}
.drawer-title {
  font-size: 38rpx;
  font-weight: 600;
  color: $color-primary;
  font-family: 'STKaiti', 'KaiTi', serif;
}
.drawer-close {
  font-size: 40rpx;
  color: $color-ink-light;
  padding: 8rpx 16rpx;
}
.drawer-loading, .drawer-empty {
  padding: 60rpx 0;
  text-align: center;
  font-size: 30rpx;
  color: $color-ink-light;
}
.drawer-list {
  flex: 1;
  min-height: 0; /* 关键：flex 子项默认 min-height:auto 会撑满父容器、让 scroll-view 拿不到剩余高度；改为 0 让 flex:1 真正生效 */
  padding: 12rpx 0;
}
.drawer-item {
  padding: 28rpx 32rpx;
  border-bottom: 1rpx solid rgba(44, 44, 44, 0.06);
  transition: background 0.2s;
}
.drawer-item.active {
  background: rgba(44, 44, 44, 0.04);
}
.drawer-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8rpx;
}
.drawer-item-title {
  font-size: 32rpx;
  color: $color-ink;
  font-weight: 500;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawer-item-del {
  font-size: 32rpx;
  color: $color-ink-light;
  padding: 4rpx 12rpx;
}
.drawer-item-msg {
  display: block;
  font-size: 28rpx;
  color: $color-ink-light;
  margin-bottom: 6rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawer-item-meta {
  display: flex;
  justify-content: space-between;
}
.drawer-item-time, .drawer-item-count {
  font-size: 26rpx;
  color: $color-ink-light;
}
.drawer-footer {
  padding: 20rpx 32rpx 30rpx;
  border-top: 1rpx solid rgba(44, 44, 44, 0.08);
}
.drawer-new-btn {
  display: block;
  text-align: center;
  padding: 22rpx 0;
  font-size: 32rpx;
  color: $color-bg-warm;
  background: $color-primary;
  border-radius: 12rpx;
}

/* 抽屉用户区 + 快捷功能 */
.drawer-profile {
  position: relative;
  display: flex;
  align-items: center;
  gap: 20rpx;
  padding: 24rpx 32rpx 20rpx;
}
.drawer-settings-btn {
  position: absolute;
  right: 24rpx;
  width: 68rpx;
  height: 68rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}
.drawer-settings-btn .dq-icon {
  width: 52rpx;
  height: 52rpx;
  font-size: 28rpx;
}
.drawer-avatar {
  width: 88rpx;
  height: 88rpx;
  line-height: 88rpx;
  text-align: center;
  border-radius: 50%;
  background: $color-primary;
  color: $color-bg;
  font-size: 40rpx;
  font-weight: 600;
  font-family: $font-family-display;
  flex-shrink: 0;
}
.drawer-profile-info {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
}
.drawer-nickname {
  font-size: 34rpx;
  font-weight: 600;
  color: $color-ink;
}
.drawer-profile-sub {
  font-size: 26rpx;
  color: $color-ink-light;
  margin-top: 4rpx;
}
.drawer-quick-scroll {
  width: 100%;
  border-bottom: 1rpx solid rgba(44, 44, 44, 0.08);
}
.drawer-quick {
  display: flex;
  gap: 20rpx;
  padding: 8rpx 32rpx 24rpx;
  width: 100%;
  box-sizing: border-box;
}
.drawer-quick-btn {
  /* 一屏恰好三个：(内容宽 - 2×gap)/3，第四个溢出走横向滑动 */
  flex: 0 0 calc((100% - 40rpx) / 3);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10rpx;
  padding: 24rpx 0;
  font-size: 30rpx;
  color: $color-ink;
  background: rgba(44, 44, 44, 0.04);
  border: 1rpx solid $color-border;
  border-radius: 16rpx;
}
.drawer-quick-btn:active {
  background: rgba(44, 44, 44, 0.08);
}
.dq-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40rpx;
  height: 40rpx;
  border-radius: 50%;
  background: $color-primary;
  color: $color-bg;
  font-size: 22rpx;
  font-family: $font-family-display;
}

/* === 省市区选择器弹窗 === */
.region-picker-mask {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  z-index: 999;
  display: flex;
  align-items: flex-end;
}
.region-picker {
  width: 100%;
  background: #fff;
  border-radius: 24rpx 24rpx 0 0;
  padding-bottom: env(safe-area-inset-bottom);
  max-height: 58vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.rp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 32rpx 12rpx;
  flex-shrink: 0;
}
.rp-tabs {
  display: flex;
  gap: 12rpx;
}
.rp-tab {
  padding: 10rpx 28rpx;
  font-size: 26rpx;
  border-radius: 30rpx;
  background: #f5f5f5;
  color: #888;
}
.rp-tab.active {
  background: #1a1a1a;
  color: #fff;
  font-weight: 600;
}
.rp-confirm {
  padding: 14rpx 36rpx;
  background: #1a1a1a;
  color: #fff;
  font-size: 26rpx;
  border-radius: 30rpx;
  font-weight: 600;
}
.rp-search {
  margin: 6rpx 32rpx 14rpx;
  display: flex;
  align-items: center;
  gap: 10rpx;
  padding: 16rpx 24rpx;
  background: #f7f7f7;
  border-radius: 12rpx;
  border: 1rpx solid #eee;
  flex-shrink: 0;
}
.rp-search-icon { font-size: 26rpx; }
.rp-search-input { flex: 1; font-size: 26rpx; }
.rp-search-ph { color: #bbb; }
.rp-col-labels {
  display: flex;
  padding: 10rpx 32rpx 6rpx;
  flex-shrink: 0;
}
.rp-col-label {
  flex: 1;
  text-align: center;
  font-size: 26rpx;
  color: #999;
  font-weight: 500;
}
/* 三列滚动容器 */
.rp-columns {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}
.rp-col {
  flex: 1;
}
.rp-item {
  display: block;
  padding: 24rpx 16rpx;
  font-size: 30rpx;
  color: #333;
  text-align: center;
  line-height: 1.5;
}
.rp-item.active {
  color: #1a1a1a;
  font-weight: 700;
  background: rgba(212,175,55,0.08);
}
</style>