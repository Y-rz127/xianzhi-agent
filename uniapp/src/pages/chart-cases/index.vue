<template>
  <view class="page">
    <view class="status-bar" :style="{ height: statusBarHeight + 'px' }"></view>

    <!-- 紫蓝渐变头部 -->
    <view class="hero">
      <view class="hero-bg"></view>
      <view class="hero-orb orb-1"></view>
      <view class="hero-orb orb-2"></view>
      <view class="hero-content">
        <text class="hero-title">命例库</text>
        <text class="hero-sub">收藏命盘 · 便捷复盘</text>
        <view class="hero-meta" v-if="cases.length">
          <text class="meta-dot">✦</text>
          <text class="meta-text">共 {{ cases.length }} 条命例</text>
        </view>
      </view>
      <text class="add-btn" @tap="openCreate">+ 新建</text>
    </view>

    <view class="body">
      <view v-if="loading && !cases.length" class="empty">
        <text class="empty-icon">✦</text>
        <text class="empty-text">星轨推演中…</text>
      </view>
      <view v-else-if="!cases.length" class="empty">
        <text class="empty-icon">✦</text>
        <text class="empty-text">尚无命例</text>
        <text class="empty-hint">点击右上角「新建」收藏命盘</text>
      </view>

      <view v-else class="list">
        <view v-for="c in cases" :key="c.id" class="case-card" @tap="loadChartCase(c)">
          <view class="case-top">
            <view class="case-head">
              <text class="case-name">{{ c.name }}</text>
              <text class="case-gender">{{ c.gender }}</text>
            </view>
            <view class="case-birth-row">
              <text class="case-birth">◷ {{ c.birthTime }}</text>
            </view>
          </view>
          <view class="tag-list" v-if="c.tags?.length">
            <text v-for="(t, i) in c.tags" :key="i" class="tag">{{ t }}</text>
          </view>
          <view class="case-actions">
            <text class="action-btn view-btn" @tap.stop="loadChartCase(c)">去排盘 ➤</text>
            <text class="action-btn export-btn" @tap.stop="exportCaseCard(c)">导出卡片</text>
            <text class="action-btn delete-btn" @tap.stop="onDelete(c)">删除</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 导出结果预览弹窗 -->
    <view v-if="posterUrl" class="modal-overlay" @tap="closePoster">
      <view class="poster-modal" @tap.stop>
        <text class="poster-title">命例卡片</text>
        <image v-if="posterUrl" class="poster-img" :src="posterUrl" mode="widthFix" />
        <view class="poster-actions">
          <text class="btn" @tap="closePoster">关闭</text>
          <text class="btn btn-primary" @tap="savePoster">保存到相册</text>
        </view>
      </view>
    </view>

    <!-- 隐藏画布（跨端绘制海报） -->
    <view class="card-canvas-wrap">
      <!-- #ifdef H5 -->
      <canvas ref="cardCanvasRef" class="card-canvas" width="600" height="900"></canvas>
      <!-- #endif -->
      <!-- #ifndef H5 -->
      <canvas canvas-id="caseCardCanvas" class="card-canvas" id="caseCardCanvas"></canvas>
      <!-- #endif -->
    </view>

    <!-- 新建命例弹窗 -->
    <view v-if="showCreate" class="modal-overlay" @tap="closeCreate">
      <view class="modal-content" @tap.stop>
        <view class="modal-header">
          <text class="modal-title">新建命例</text>
          <text class="modal-close" @tap="closeCreate">✕</text>
        </view>
        <view class="modal-body">
          <view class="form-row">
            <text class="label">名称</text>
            <input class="input" v-model="form.name" placeholder="如：我的命盘" cursor-spacing="120" confirm-type="next" @tap.stop />
          </view>
          <view class="form-row">
            <text class="label">出生日期</text>
            <picker class="picker-wrap" mode="date" :value="form.date || today" :end="today" @change="onDateChange">
              <view :class="['picker', form.date && 'selected']">
                <text class="picker-text">{{ form.date || '选择日期' }}</text>
              </view>
            </picker>
          </view>

          <view class="form-row">
            <text class="label">出生时辰</text>
            <picker class="picker-wrap" mode="time" :value="form.time || '00:00'" @change="onTimeChange">
              <view :class="['picker', form.time && 'selected']">
                <text class="picker-text">{{ form.time || '选择时间' }}</text>
              </view>
            </picker>
          </view>

          <view class="form-row">
            <text class="label">性别</text>
            <view class="gender-group">
              <text :class="['gender', form.gender === '男' && 'active']" @tap="form.gender = '男'">男</text>
              <text :class="['gender', form.gender === '女' && 'active']" @tap="form.gender = '女'">女</text>
            </view>
          </view>
          <view class="form-row">
            <text class="label">标签</text>
            <input class="input" v-model="form.tags" placeholder="逗号分隔，如：事业,婚姻" cursor-spacing="120" confirm-type="done" @tap.stop />
          </view>
        </view>
        <view class="modal-footer">
          <text class="btn" @tap="closeCreate">取消</text>
          <text :class="['btn', 'btn-primary', !canSave && 'disabled']" @tap="onSave">保存</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { fetchChartCases, createChartCase, deleteChartCase, type ChartCase } from '@/api'
import { getLocalDateString } from '@/utils/datetimePicker'

const statusBarHeight = ref(20)
try {
  const sysInfo = uni.getWindowInfo()
  statusBarHeight.value = sysInfo.statusBarHeight || 20
} catch {}

const cases = ref<ChartCase[]>([])
const loading = ref(false)
const showCreate = ref(false)
const today = getLocalDateString()

const form = reactive({
  name: '',
  date: '',
  time: '',
  gender: '男' as '男' | '女',
  tags: '',
})

const canSave = computed(() => form.name.trim() && form.date && form.time)

function onDateChange(e: any) { form.date = e.detail.value }
function onTimeChange(e: any) { form.time = e.detail.value }

async function load() {
  loading.value = true
  try {
    cases.value = await fetchChartCases()
  } catch {
    cases.value = []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.name = ''
  form.date = ''
  form.time = ''
  form.gender = '男'
  form.tags = ''
  showCreate.value = true
}

function closeCreate() {
  showCreate.value = false
}

async function onSave() {
  if (!canSave.value) return
  const birthTime = `${form.date} ${form.time}`
  try {
    uni.showLoading({ title: '排盘中…' })
    await createChartCase({
      name: form.name.trim(),
      birthTime,
      gender: form.gender,
      tags: form.tags.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
    })
    uni.hideLoading()
    uni.showToast({ title: '保存成功', icon: 'success' })
    showCreate.value = false
    load()
  } catch (e: any) {
    uni.hideLoading()
    uni.showToast({ title: e.message || '保存失败', icon: 'none' })
  }
}

async function onDelete(c: ChartCase) {
  const res = await new Promise<boolean>((resolve) => {
    uni.showModal({
      title: '确认删除',
      content: `删除命例「${c.name}」？`,
      success: (r) => resolve(r.confirm),
    })
  })
  if (!res) return
  try {
    await deleteChartCase(c.id)
    uni.showToast({ title: '已删除', icon: 'success' })
    load()
  } catch (e: any) {
    uni.showToast({ title: e.message || '删除失败', icon: 'none' })
  }
}

function loadChartCase(c: ChartCase) {
  uni.navigateTo({
    url: `/pages/xianzhi/index?birthTime=${encodeURIComponent(c.birthTime)}&gender=${encodeURIComponent(c.gender)}&name=${encodeURIComponent(c.name)}`,
  })
}

// ---------- 导出内容卡片 ----------
const posterUrl = ref('')
const currentPosterCase = ref<ChartCase | null>(null)
const cardCanvasRef = ref<HTMLCanvasElement | null>(null)

function hexToRgba(hex: string, alpha: number) {
  const h = hex.replace('#', '')
  const r = parseInt(h.substring(0, 2), 16)
  const g = parseInt(h.substring(2, 4), 16)
  const b = parseInt(h.substring(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function drawRoundRect(ctx: any, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function drawPoster(ctx: any, width: number, height: number, c: ChartCase) {
  // 背景
  const bgGradient = ctx.createLinearGradient(0, 0, width, height)
  bgGradient.addColorStop(0, '#1E1638')
  bgGradient.addColorStop(0.5, '#160F2E')
  bgGradient.addColorStop(1, '#0F0B1E')
  ctx.fillStyle = bgGradient
  ctx.fillRect(0, 0, width, height)

  // 顶部光晕
  const glowGradient = ctx.createRadialGradient(width * 0.5, height * 0.25, 0, width * 0.5, height * 0.25, width * 0.8)
  glowGradient.addColorStop(0, hexToRgba('#7C3AED', 0.25))
  glowGradient.addColorStop(0.5, hexToRgba('#06B6D4', 0.08))
  glowGradient.addColorStop(1, hexToRgba('#7C3AED', 0))
  ctx.fillStyle = glowGradient
  ctx.fillRect(0, 0, width, height)

  // 边框
  ctx.strokeStyle = hexToRgba('#7C3AED', 0.35)
  ctx.lineWidth = 4
  drawRoundRect(ctx, 24, 24, width - 48, height - 48, 24)
  ctx.stroke()

  // 顶部装饰线
  const lineGradient = ctx.createLinearGradient(60, 0, width - 60, 0)
  lineGradient.addColorStop(0, hexToRgba('#7C3AED', 0))
  lineGradient.addColorStop(0.5, '#06B6D4')
  lineGradient.addColorStop(1, hexToRgba('#7C3AED', 0))
  ctx.strokeStyle = lineGradient
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(60, 90)
  ctx.lineTo(width - 60, 90)
  ctx.stroke()

  // 标题
  ctx.fillStyle = '#FFFFFF'
  ctx.font = 'bold 44px sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText('✦ 先知命盘', width / 2, 160)

  // 分隔符
  ctx.fillStyle = hexToRgba('#C4B5FD', 0.4)
  ctx.font = '28px sans-serif'
  ctx.fillText('━━━━━━━━━━━━', width / 2, 220)

  // 命例名称
  ctx.fillStyle = '#F59E0B'
  ctx.font = 'bold 52px sans-serif'
  ctx.fillText(c.name, width / 2, 320)

  // 信息卡片背景
  ctx.fillStyle = hexToRgba('#FFFFFF', 0.05)
  drawRoundRect(ctx, 60, 380, width - 120, 220, 20)
  ctx.fill()

  // 出生时间
  ctx.fillStyle = '#C4B5FD'
  ctx.font = '28px sans-serif'
  ctx.textAlign = 'left'
  ctx.fillText('出生时间', 100, 440)
  ctx.fillStyle = '#FFFFFF'
  ctx.font = '36px sans-serif'
  ctx.fillText(c.birthTime, 100, 490)

  // 性别
  ctx.fillStyle = '#C4B5FD'
  ctx.font = '28px sans-serif'
  ctx.fillText('性别', 100, 550)
  ctx.fillStyle = '#06B6D4'
  ctx.font = '36px sans-serif'
  ctx.fillText(c.gender, 100, 595)

  // 标签
  if (c.tags?.length) {
    ctx.textAlign = 'center'
    ctx.font = '24px sans-serif'
    const tagText = c.tags.slice(0, 4).join('  ·  ')
    ctx.fillStyle = hexToRgba('#F59E0B', 0.9)
    ctx.fillText(tagText, width / 2, 690)
  }

  // 底部文字
  ctx.fillStyle = hexToRgba('#C4B5FD', 0.6)
  ctx.font = '24px sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText('先知 · 知命不惑', width / 2, 820)
}

async function exportCaseCard(c: ChartCase) {
  currentPosterCase.value = c
  uni.showLoading({ title: '生成卡片中…' })
  try {
    const url = await generatePoster(c)
    posterUrl.value = url
  } catch (e: any) {
    uni.showToast({ title: e.message || '生成失败', icon: 'none' })
  } finally {
    uni.hideLoading()
  }
}

function generatePoster(c: ChartCase): Promise<string> {
  return new Promise((resolve, reject) => {
    // #ifdef H5
    const canvas = cardCanvasRef.value
    if (!canvas) return reject(new Error('canvas not found'))
    const ctx = canvas.getContext('2d')
    if (!ctx) return reject(new Error('canvas context not found'))
    const dpr = window.devicePixelRatio || 1
    canvas.width = 600 * dpr
    canvas.height = 900 * dpr
    ctx.scale(dpr, dpr)
    drawPoster(ctx, 600, 900, c)
    resolve(canvas.toDataURL('image/png'))
    // #endif

    // #ifndef H5
    const ctx2 = uni.createCanvasContext('caseCardCanvas')
    drawPoster(ctx2, 600, 900, c)
    ctx2.draw(false, () => {
      uni.canvasToTempFilePath({
        canvasId: 'caseCardCanvas',
        width: 600,
        height: 900,
        destWidth: 600,
        destHeight: 900,
        success: (res) => resolve(res.tempFilePath),
        fail: (err) => reject(new Error(err.errMsg || '导出失败')),
      })
    })
    // #endif
  })
}

function closePoster() {
  posterUrl.value = ''
  currentPosterCase.value = null
}

function savePoster() {
  if (!posterUrl.value) return
  // #ifdef H5
  const a = document.createElement('a')
  a.href = posterUrl.value
  a.download = `先知命盘_${currentPosterCase.value?.name || '命例'}.png`
  a.click()
  // #endif

  // #ifndef H5
  uni.saveImageToPhotosAlbum({
    filePath: posterUrl.value,
    success: () => uni.showToast({ title: '已保存到相册', icon: 'success' }),
    fail: (err) => {
      if (err.errMsg?.includes('auth deny') || err.errMsg?.includes('authorize')) {
        uni.showModal({
          title: '需要授权',
          content: '请允许保存图片到相册',
          success: (r) => {
            if (r.confirm) uni.openSetting()
          },
        })
      } else {
        uni.showToast({ title: err.errMsg || '保存失败', icon: 'none' })
      }
    },
  })
  // #endif
}

onMounted(load)
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  background: #0F0B1E;
  display: flex;
  flex-direction: column;
}

/* 状态栏占位 */
.status-bar { width: 100%; }

/* 紫蓝渐变头部 */
.hero {
  position: relative;
  padding: 40rpx 32rpx 60rpx;
  overflow: hidden;
  background: linear-gradient(135deg, #2D1B5E 0%, #1A1238 100%);
  border-bottom-left-radius: 48rpx;
  border-bottom-right-radius: 48rpx;
}
.hero-bg {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background:
    radial-gradient(circle at 20% 30%, rgba(124, 58, 237, 0.4), transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(6, 182, 212, 0.25), transparent 50%);
}
.hero-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40rpx);
  pointer-events: none;
}
.orb-1 {
  top: -60rpx; right: -40rpx;
  width: 200rpx; height: 200rpx;
  background: rgba(124, 58, 237, 0.5);
}
.orb-2 {
  bottom: -80rpx; left: -60rpx;
  width: 220rpx; height: 220rpx;
  background: rgba(6, 182, 212, 0.35);
}
.hero-content { position: relative; z-index: 1; }
.hero-title {
  display: block;
  font-size: 52rpx;
  font-weight: 800;
  color: #FFFFFF;
  letter-spacing: 8rpx;
  text-shadow: 0 0 24rpx rgba(124, 58, 237, 0.6);
}
.hero-sub {
  display: block;
  margin-top: 12rpx;
  font-size: 24rpx;
  color: rgba(196, 181, 253, 0.9);
  letter-spacing: 4rpx;
}
.hero-meta {
  display: flex;
  align-items: center;
  margin-top: 20rpx;
}
.meta-dot {
  color: #06B6D4;
  font-size: 20rpx;
  margin-right: 10rpx;
}
.meta-text {
  font-size: 22rpx;
  color: rgba(196, 181, 253, 0.8);
  letter-spacing: 2rpx;
}
.add-btn {
  position: absolute;
  top: 40rpx;
  right: 32rpx;
  z-index: 2;
  font-size: 26rpx;
  color: #FFFFFF;
  padding: 12rpx 28rpx;
  background: linear-gradient(135deg, #7C3AED, #06B6D4);
  border-radius: 32rpx;
  box-shadow: 0 4rpx 20rpx rgba(124, 58, 237, 0.5);
  letter-spacing: 4rpx;
}

/* 主体 */
.body {
  flex: 1;
  padding: 24rpx;
}

/* 空状态 */
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 120rpx 0;
}
.empty-icon {
  font-size: 80rpx;
  color: #7C3AED;
  margin-bottom: 24rpx;
  text-shadow: 0 0 24rpx rgba(124, 58, 237, 0.6);
}
.empty-text {
  font-size: 30rpx;
  color: #C4B5FD;
  margin-bottom: 8rpx;
  letter-spacing: 4rpx;
}
.empty-hint {
  font-size: 24rpx;
  color: #6B7280;
}

/* 命例卡片列表 */
.list {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}
.case-card {
  position: relative;
  background: rgba(30, 22, 56, 0.8);
  backdrop-filter: blur(24rpx);
  -webkit-backdrop-filter: blur(24rpx);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 32rpx;
  padding: 28rpx;
  overflow: hidden;
}
.case-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2rpx;
  background: linear-gradient(90deg, transparent, #7C3AED, #06B6D4, transparent);
}
.case-top {
  display: flex;
  flex-direction: column;
}
.case-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10rpx;
}
.case-name {
  font-size: 32rpx;
  font-weight: 600;
  color: #FFFFFF;
  letter-spacing: 4rpx;
}
.case-gender {
  font-size: 22rpx;
  color: #06B6D4;
  background: rgba(6, 182, 212, 0.12);
  border: 1rpx solid rgba(6, 182, 212, 0.4);
  padding: 6rpx 20rpx;
  border-radius: 24rpx;
}
.case-birth-row { display: flex; align-items: center; }
.case-birth {
  font-size: 24rpx;
  color: #C4B5FD;
  letter-spacing: 2rpx;
}

/* 标签 */
.tag-list {
  display: flex;
  flex-wrap: wrap;
  margin-top: 16rpx;
}
.tag {
  font-size: 20rpx;
  color: #F59E0B;
  background: rgba(245, 158, 11, 0.1);
  border: 1rpx solid rgba(245, 158, 11, 0.3);
  padding: 4rpx 16rpx;
  border-radius: 20rpx;
  margin: 8rpx 12rpx 0 0;
  letter-spacing: 1rpx;
}

/* 操作按钮 */
.case-actions {
  display: flex;
  justify-content: flex-end;
  gap: 16rpx;
  margin-top: 20rpx;
  padding-top: 20rpx;
  border-top: 1rpx solid rgba(124, 58, 237, 0.15);
}
.action-btn {
  font-size: 24rpx;
  padding: 10rpx 28rpx;
  border-radius: 24rpx;
  letter-spacing: 2rpx;
}
.view-btn {
  color: #FFFFFF;
  background: linear-gradient(135deg, #7C3AED, #06B6D4);
  box-shadow: 0 4rpx 16rpx rgba(124, 58, 237, 0.4);
}
.export-btn {
  color: #F59E0B;
  background: rgba(245, 158, 11, 0.1);
  border: 1rpx solid rgba(245, 158, 11, 0.3);
}
.delete-btn {
  color: #9CA3AF;
  background: rgba(156, 163, 175, 0.08);
  border: 1rpx solid rgba(156, 163, 175, 0.2);
}

/* 隐藏画布 */
.card-canvas-wrap {
  position: fixed;
  left: -2000rpx;
  top: -2000rpx;
  opacity: 0;
  pointer-events: none;
  z-index: -1;
}
.card-canvas {
  width: 600px;
  height: 900px;
}

/* 海报预览弹窗 */
.poster-modal {
  width: 84%;
  max-width: 640rpx;
  background: linear-gradient(180deg, #1E1638 0%, #160F2E 100%);
  border: 1rpx solid rgba(124, 58, 237, 0.3);
  border-radius: 32rpx;
  padding: 32rpx;
  box-shadow: 0 24rpx 64rpx rgba(0, 0, 0, 0.6), 0 0 64rpx rgba(124, 58, 237, 0.2);
}
.poster-title {
  display: block;
  font-size: 32rpx;
  font-weight: 600;
  color: #FFFFFF;
  text-align: center;
  letter-spacing: 4rpx;
  margin-bottom: 24rpx;
}
.poster-img {
  width: 100%;
  border-radius: 20rpx;
  border: 1rpx solid rgba(124, 58, 237, 0.2);
}
.poster-actions {
  display: flex;
  gap: 20rpx;
  margin-top: 28rpx;
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(15, 11, 30, 0.85);
  backdrop-filter: blur(20rpx);
  -webkit-backdrop-filter: blur(20rpx);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-content {
  width: 90%;
  box-sizing: border-box;
  background: linear-gradient(180deg, #1E1638 0%, #160F2E 100%);
  border: 1rpx solid rgba(124, 58, 237, 0.3);
  border-radius: 32rpx;
  overflow: hidden;
  box-shadow: 0 24rpx 64rpx rgba(0, 0, 0, 0.6), 0 0 64rpx rgba(124, 58, 237, 0.2);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  box-sizing: border-box;
  padding: 28rpx 32rpx;
  border-bottom: 1rpx solid rgba(124, 58, 237, 0.2);
}
.modal-title {
  font-size: 32rpx;
  font-weight: 600;
  color: #FFFFFF;
  letter-spacing: 4rpx;
}
.modal-close {
  font-size: 36rpx;
  color: #C4B5FD;
  padding: 8rpx 16rpx;
}
.modal-body {
  width: 100%;
  box-sizing: border-box;
  padding: 28rpx 32rpx;
}
.form-row {
  display: flex;
  align-items: center;
  margin-bottom: 24rpx;
  font-size: 26rpx;
  width: 100%;
  box-sizing: border-box;
}
.label {
  flex: 0 0 140rpx;
  color: #C4B5FD;
  letter-spacing: 2rpx;
}
.input {
  flex: 1;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
  height: 68rpx;
  line-height: 68rpx;
  padding: 0 20rpx;
  background: rgba(124, 58, 237, 0.08);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 16rpx;
  color: #FFFFFF;
  font-size: 26rpx;
}
.picker-wrap {
  flex: 1;
  min-width: 0;
  display: block;
}
.picker {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  height: 68rpx;
  line-height: 68rpx;
  padding: 0 20rpx;
  background: rgba(124, 58, 237, 0.08);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 16rpx;
  color: #FFFFFF;
  font-size: 26rpx;
  overflow: hidden;
}
.picker.selected {
  border-color: #7C3AED;
  background: rgba(124, 58, 237, 0.18);
}
.picker-text {
  display: block;
  height: 68rpx;
  line-height: 68rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gender-group {
  flex: 1;
  min-width: 0;
  display: flex;
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 16rpx;
  overflow: hidden;
}
.gender {
  flex: 1;
  text-align: center;
  padding: 16rpx 0;
  font-size: 26rpx;
  color: #94A3B8;
  background: rgba(124, 58, 237, 0.06);
}
.gender.active {
  background: rgba(124, 58, 237, 0.25);
  color: #C4B5FD;
}
.modal-footer {
  display: flex;
  gap: 20rpx;
  width: 100%;
  box-sizing: border-box;
  padding: 24rpx 32rpx 32rpx;
  border-top: 1rpx solid rgba(124, 58, 237, 0.2);
}
.btn {
  flex: 1;
  text-align: center;
  padding: 20rpx 0;
  color: #C4B5FD;
  background: rgba(124, 58, 237, 0.1);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 24rpx;
  font-size: 28rpx;
}
.btn-primary {
  color: #FFFFFF;
  background: linear-gradient(135deg, #7C3AED, #06B6D4);
  border: none;
  box-shadow: 0 4rpx 20rpx rgba(124, 58, 237, 0.4);
}
.btn.disabled,
.btn-primary.disabled {
  opacity: 0.45;
}
</style>
