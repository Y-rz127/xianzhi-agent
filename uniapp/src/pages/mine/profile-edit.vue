<template>
  <view class="page">
    <view class="body">
      <view class="form-row">
        <text class="label">名称</text>
        <input class="input" v-model="form.name" placeholder="如：我自己 / 老公 / 宝宝" maxlength="20" />
      </view>
      <view class="form-row">
        <text class="label">关系</text>
        <input class="input" v-model="form.relation" placeholder="如：本人 / 配偶 / 朋友" maxlength="10" />
      </view>
      <view class="form-row">
        <text class="label">出生日期</text>
        <picker mode="date" :value="form.date" :end="today" @change="onDate">
          <view :class="['picker', form.date && 'selected']">
            <text class="picker-text">{{ form.date || '选择日期' }}</text>
          </view>
        </picker>
      </view>
      <view class="form-row">
        <text class="label">出生时辰</text>
        <picker mode="time" :value="form.time" @change="onTime">
          <view :class="['picker', form.time && 'selected']">
            <text class="picker-text">{{ form.time || '选择时间' }}</text>
          </view>
        </picker>
      </view>
      <view class="form-row">
        <text class="label">性别</text>
        <view class="seg-group">
          <text :class="['seg', form.gender === '男' && 'active']" @tap="form.gender = '男'">男</text>
          <text :class="['seg', form.gender === '女' && 'active']" @tap="form.gender = '女'">女</text>
        </view>
      </view>
      <view class="form-row">
        <text class="label">子时派</text>
        <view class="seg-group">
          <text :class="['seg', form.sect === 2 && 'active']" @tap="form.sect = 2">晚子时</text>
          <text :class="['seg', form.sect === 1 && 'active']" @tap="form.sect = 1">早子时</text>
        </view>
      </view>
      <view class="hint">保存后可在「我的」页一键带入先知对话。</view>
      <button class="submit-btn" @tap="onSave">保存</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { createProfile, updateProfile, type BaziProfile } from '@/api'
import { getLocalDateString } from '@/utils/datetimePicker'

const today = getLocalDateString()
const isEdit = ref(false)
const editId = ref('')
const form = reactive({
  name: '',
  relation: '',
  date: '',
  time: '',
  gender: '男' as '男' | '女',
  sect: 2,
})

onLoad((q) => {
  if (q && q.id) {
    isEdit.value = true
    editId.value = q.id
    const raw = decodeURIComponent(q.data || '{}')
    try {
      const p = JSON.parse(raw) as BaziProfile
      form.name = p.name
      form.relation = p.relation
      form.gender = (p.gender as '男' | '女') || '男'
      form.sect = p.sect || 2
      const [d, t] = (p.birthTime || '').split(' ')
      form.date = d || ''
      form.time = t || ''
    } catch {}
  }
})

function onDate(e: any) { form.date = e.detail.value }
function onTime(e: any) { form.time = e.detail.value }

async function onSave() {
  if (!form.name.trim()) { uni.showToast({ title: '请填写名称', icon: 'none' }); return }
  if (!form.date || !form.time) { uni.showToast({ title: '请选择出生日期和时间', icon: 'none' }); return }
  const birthTime = `${form.date} ${form.time}`
  const payload: Partial<BaziProfile> = {
    name: form.name.trim(),
    relation: form.relation.trim(),
    birthTime,
    gender: form.gender,
    sect: form.sect,
    yunSect: 1,
  }
  try {
    uni.showLoading({ title: '保存中…' })
    if (isEdit.value) await updateProfile(editId.value, payload)
    else await createProfile(payload)
    uni.hideLoading()
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 500)
  } catch (e: any) {
    uni.hideLoading()
    uni.showToast({ title: e?.message || '保存失败', icon: 'none' })
  }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: $color-bg; display: flex; flex-direction: column; }
.body { flex: 1; padding: 32rpx 32rpx 64rpx; }
.form-row { display: flex; align-items: center; margin-bottom: 28rpx; }
.label { flex: 0 0 140rpx; font-size: 26rpx; color: $color-ink-light; }
.input {
  flex: 1; padding: 20rpx 24rpx; background: rgba(107, 123, 142, 0.06);
  border: 1rpx solid $color-border; border-radius: 20rpx; font-size: 28rpx; color: $color-ink;
}
.picker {
  flex: 1; display: flex; align-items: center; padding: 20rpx 24rpx;
  background: rgba(107, 123, 142, 0.06); border: 1rpx solid $color-border; border-radius: 20rpx;
}
.picker.selected { border-color: $color-primary; }
.picker-text { font-size: 28rpx; color: $color-ink; }
.seg-group { flex: 1; display: flex; border: 1rpx solid $color-border; border-radius: 20rpx; overflow: hidden; }
.seg { flex: 1; text-align: center; padding: 18rpx 0; font-size: 26rpx; color: $color-ink-light; background: rgba(107, 123, 142, 0.04); }
.seg.active { background: rgba(107, 123, 142, 0.18); color: $color-primary; }
.hint { font-size: 22rpx; color: $color-ink-lighter; margin-top: 12rpx; line-height: 1.6; }
.submit-btn {
  margin-top: 40rpx;
  width: 100%;
  height: 88rpx;
  line-height: 88rpx;
  text-align: center;
  background: linear-gradient(135deg, #6b7b8e 0%, #4a5a6a 100%);
  color: #fff;
  font-size: 30rpx;
  font-weight: 600;
  border-radius: 44rpx;
  border: none;
  &::after { border: none; }
  &:active { transform: scale(0.98); opacity: 0.85; }
}
</style>
