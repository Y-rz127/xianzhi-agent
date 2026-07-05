<template>
  <view v-if="visible" class="modal-overlay" @tap="close">
    <view class="modal-content" @tap.stop>
      <!-- 头部 -->
      <view class="modal-header">
        <text class="modal-title">命盘详情</text>
        <text class="modal-close" @tap="close">✕</text>
      </view>

      <!-- 内容区 -->
      <scroll-view class="modal-body" scroll-y>
        <!-- 四柱 -->
        <view class="section" v-if="pillars.length">
          <text class="section-title">四柱命盘</text>
          <view class="pillars-grid">
            <view
              v-for="p in pillars"
              :key="p.name"
              :class="['pillar-card', p.name === '日柱' && 'day-master']"
            >
              <text class="pillar-name">{{ p.name }}</text>
              <text class="pillar-gan">{{ p.ganzhi[0] }}</text>
              <text class="pillar-zhi">{{ p.ganzhi[1] }}</text>
              <text class="pillar-nayin">{{ p.nayin }}</text>
            </view>
          </view>
        </view>

        <!-- 五行 -->
        <view class="section" v-if="wuxing.length">
          <text class="section-title">五行分布</text>
          <view class="wuxing-grid">
            <view v-for="w in wuxing" :key="w.name" class="wuxing-item">
              <view class="wuxing-bar-container">
                <view
                  class="wuxing-bar"
                  :style="{ height: (w.count / maxWuxing * 100) + '%', background: w.color }"
                ></view>
              </view>
              <text class="wuxing-label" :style="{ color: w.color }">{{ w.name }}</text>
              <text class="wuxing-count">{{ w.count }}</text>
            </view>
          </view>
        </view>

        <!-- 大运 -->
        <view class="section" v-if="dayun.length">
          <text class="section-title">大运</text>
          <view class="dayun-grid">
            <view v-for="(d, i) in dayun" :key="i" class="dayun-card">
              <text class="dayun-year">{{ d.year }}</text>
              <text class="dayun-range">{{ d.startYear }}-{{ d.startYear + 9 }}</text>
              <text class="dayun-age">{{ d.startAge }}-{{ d.startAge + 9 }}岁</text>
            </view>
          </view>
        </view>

        <!-- 神煞 -->
        <view class="section" v-if="shensha.length">
          <text class="section-title">神煞</text>
          <view class="shensha-list">
            <view v-for="(s, i) in shensha" :key="i" class="shensha-item">
              <text class="shensha-name">{{ s.name }}</text>
              <text class="shensha-desc">{{ s.description }}</text>
            </view>
          </view>
        </view>

        <!-- AI 报告 -->
        <view class="section">
          <text class="section-title">AI 命理报告</text>
          <view v-if="reportLoading" class="report-loading">
            <text>正在由先知生成报告…</text>
          </view>
          <view v-else-if="reportContent" class="report-content">
            <MarkdownRender :content="reportContent" />
          </view>
          <view v-else class="report-placeholder">
            <text>点击下方按钮生成 AI 分节命理报告</text>
          </view>
        </view>
      </scroll-view>

      <!-- 底部操作栏 -->
      <view class="modal-footer">
        <text class="btn" @tap="handleDownloadPdf">下载 PDF</text>
        <text
          :class="['btn', 'btn-primary', reportLoading && 'disabled']"
          @tap="generateReport"
        >{{ reportLoading ? '生成中…' : '生成完整报告' }}</text>
        <text v-if="reportContent" class="btn" @tap="downloadFullPdf">导出完整 PDF</text>
        <text class="btn" @tap="close">关闭</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Pillar, WuxingItem, DayunItem, ShenshaItem } from '@/api'
import { generateFullReport, downloadReport, downloadFullReportPdf } from '@/api'

const props = defineProps<{
  visible: boolean
  pillars: Pillar[]
  wuxing: WuxingItem[]
  dayun: DayunItem[]
  shensha: ShenshaItem[]
  birthTime?: string
  gender?: string
}>()
const emit = defineEmits<{ close: [] }>()

const reportContent = ref('')
const reportLoading = ref(false)

const maxWuxing = computed(() => Math.max(...props.wuxing.map((w) => w.count), 1))

function close() {
  emit('close')
}

function handleDownloadPdf() {
  if (!props.birthTime || !props.gender) {
    uni.showToast({ title: '缺少出生信息', icon: 'none' })
    return
  }
  downloadReport(props.birthTime, props.gender)
}

function downloadFullPdf() {
  if (!props.birthTime || !props.gender) return
  downloadFullReportPdf(props.birthTime, props.gender)
}

async function generateReport() {
  if (!props.birthTime || !props.gender || reportLoading.value) return
  reportLoading.value = true
  reportContent.value = ''
  try {
    const res = await generateFullReport(props.birthTime, props.gender)
    reportContent.value = res.content || ''
  } catch (e: any) {
    reportContent.value = `报告生成失败：${e.message || '请稍后重试'}`
  } finally {
    reportLoading.value = false
  }
}
</script>

<style lang="scss" scoped>
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
  width: 92%;
  max-height: 85vh;
  background: linear-gradient(180deg, #1E1638 0%, #160F2E 100%);
  border: 1rpx solid rgba(124, 58, 237, 0.3);
  border-radius: 32rpx;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24rpx 64rpx rgba(0, 0, 0, 0.6), 0 0 64rpx rgba(124, 58, 237, 0.2);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
  padding: 28rpx 32rpx;
  max-height: 65vh;
}

.section {
  margin-bottom: 32rpx;
}
.section-title {
  display: block;
  font-size: 26rpx;
  color: #06B6D4;
  letter-spacing: 6rpx;
  font-weight: 600;
  margin-bottom: 20rpx;
  padding-bottom: 12rpx;
  border-bottom: 1rpx solid rgba(124, 58, 237, 0.15);
}

/* 四柱 */
.pillars-grid {
  display: flex;
  justify-content: space-between;
}
.pillar-card {
  flex: 1;
  margin: 0 6rpx;
  background: rgba(124, 58, 237, 0.06);
  border-radius: 16rpx;
  padding: 20rpx 8rpx;
  text-align: center;
  border: 1rpx solid rgba(124, 58, 237, 0.18);
}
.pillar-card.day-master {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(124, 58, 237, 0.08));
  border-color: rgba(245, 158, 11, 0.4);
  box-shadow: 0 0 16rpx rgba(245, 158, 11, 0.15);
}
.pillar-name {
  display: block;
  font-size: 20rpx;
  color: #94A3B8;
  margin-bottom: 12rpx;
  letter-spacing: 2rpx;
}
.pillar-gan {
  display: block;
  font-size: 40rpx;
  font-weight: bold;
  color: #FFFFFF;
  letter-spacing: 4rpx;
  margin-bottom: 4rpx;
}
.pillar-card.day-master .pillar-gan { color: #F59E0B; }
.pillar-zhi {
  display: block;
  font-size: 32rpx;
  color: #C4B5FD;
  margin-bottom: 8rpx;
  letter-spacing: 4rpx;
}
.pillar-card.day-master .pillar-zhi { color: #F59E0B; }
.pillar-nayin {
  display: block;
  font-size: 20rpx;
  color: #6B7280;
}

/* 五行 */
.wuxing-grid {
  display: flex;
  justify-content: space-around;
  align-items: flex-end;
  height: 220rpx;
}
.wuxing-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 18%;
}
.wuxing-bar-container {
  width: 100%;
  height: 140rpx;
  display: flex;
  align-items: flex-end;
  background: rgba(124, 58, 237, 0.06);
  border-radius: 12rpx 12rpx 0 0;
  overflow: hidden;
}
.wuxing-bar {
  width: 100%;
  border-radius: 12rpx 12rpx 0 0;
  min-height: 6rpx;
}
.wuxing-label {
  font-size: 26rpx;
  font-weight: bold;
  margin-top: 8rpx;
}
.wuxing-count {
  font-size: 22rpx;
  color: #94A3B8;
}

/* 大运 */
.dayun-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
}
.dayun-card {
  width: 23%;
  background: rgba(124, 58, 237, 0.06);
  border-radius: 16rpx;
  padding: 16rpx 8rpx;
  text-align: center;
  border: 1rpx solid rgba(124, 58, 237, 0.18);
}
.dayun-year {
  display: block;
  font-size: 30rpx;
  font-weight: bold;
  color: #06B6D4;
  margin-bottom: 6rpx;
  letter-spacing: 2rpx;
}
.dayun-range {
  display: block;
  font-size: 20rpx;
  color: #94A3B8;
  margin-bottom: 2rpx;
}
.dayun-age {
  display: block;
  font-size: 20rpx;
  color: #6B7280;
}

/* 神煞 */
.shensha-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
}
.shensha-item {
  width: 48%;
  background: rgba(124, 58, 237, 0.06);
  border-radius: 16rpx;
  padding: 16rpx;
  border: 1rpx solid rgba(124, 58, 237, 0.18);
}
.shensha-name {
  display: block;
  font-size: 24rpx;
  color: #F59E0B;
  font-weight: 600;
  margin-bottom: 6rpx;
  letter-spacing: 2rpx;
}
.shensha-desc {
  display: block;
  font-size: 22rpx;
  color: #C4B5FD;
  line-height: 1.5;
}

/* 报告 */
.report-loading {
  padding: 32rpx;
  text-align: center;
  color: #06B6D4;
  font-size: 26rpx;
  letter-spacing: 2rpx;
}
.report-placeholder {
  padding: 32rpx;
  text-align: center;
  color: #6B7280;
  font-size: 24rpx;
}
.report-content {
  background: rgba(124, 58, 237, 0.06);
  border: 1rpx solid rgba(124, 58, 237, 0.18);
  border-radius: 16rpx;
  padding: 24rpx;
}

/* 底部 */
.modal-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  padding: 24rpx 32rpx;
  border-top: 1rpx solid rgba(124, 58, 237, 0.2);
}
.btn {
  flex: 1;
  min-width: 180rpx;
  text-align: center;
  padding: 18rpx 16rpx;
  background: rgba(196, 181, 253, 0.08);
  border: 1rpx solid rgba(124, 58, 237, 0.2);
  border-radius: 20rpx;
  font-size: 26rpx;
  color: #C4B5FD;
  letter-spacing: 2rpx;
}
.btn-primary {
  background: linear-gradient(135deg, #7C3AED, #06B6D4);
  color: #FFFFFF;
  border-color: transparent;
  box-shadow: 0 4rpx 16rpx rgba(124, 58, 237, 0.5);
}
.btn.disabled { opacity: 0.4; }
</style>
