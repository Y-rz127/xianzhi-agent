<template>
  <view :class="['page-root', themeClass]">
    <!-- 自定义导航 -->
    <view class="navbar" :style="{ paddingTop: statusBarHeight + 'px' }">
      <view class="navbar-inner">
        <text class="nav-back" @tap="goBack">‹ 返回</text>
        <text class="nav-title display-font">命理 K 线</text>
        <text class="nav-back nav-ghost">&#8203;</text>
      </view>
    </view>

    <!-- 维度切换：取象不同、刻度相同（后端已把侧重表均值归一） -->
    <scroll-view v-if="dimensions.length" class="dim-bar" scroll-x :show-scrollbar="false">
      <view class="dim-row">
        <text
          v-for="d in dimensions"
          :key="d.key"
          :class="['dim-btn', d.key === dimension && 'dim-active']"
          @tap="switchDimension(d.key)"
        >{{ d.label }}</text>
      </view>
    </scroll-view>

    <view v-if="loading" class="page-state">正在计算一生运势…</view>
    <view v-else-if="error" class="page-state">{{ error }}</view>
    <view v-else-if="!candles.length" class="page-state">
      缺少出生信息，无法计算 K 线。请从先知对话、档案或命例库进入。
    </view>

    <scroll-view v-else class="page-body" scroll-y>
      <!-- 概览 -->
      <view class="card">
        <view class="ov-grid">
          <view class="ov-cell">
            <text class="ov-label">日主</text>
            <text class="ov-value">{{ favor.dayMaster }}{{ favor.dayMasterWuxing }}</text>
          </view>
          <view class="ov-cell">
            <text class="ov-label">强弱</text>
            <text class="ov-value">{{ favor.strength }}</text>
          </view>
          <view class="ov-cell">
            <text class="ov-label">格局</text>
            <text class="ov-value">{{ favor.specialPattern || '正格' }}</text>
          </view>
          <view class="ov-cell">
            <text class="ov-label">最喜 / 最忌</text>
            <text class="ov-value">{{ favor.mostFavored }} / {{ favor.mostOpposed }}</text>
          </view>
        </view>
        <text v-if="meta.dimensionNote" class="ov-note">{{ meta.dimensionNote }}</text>
        <!-- 病药说明：解释「最喜/最忌」为何这样定。无病则整行不出现 -->
        <text v-if="favor.ailmentNote" class="ov-note ov-ailment">{{ favor.ailmentNote }}</text>
        <view class="ov-stats">
          <text class="ov-stat">覆盖 {{ meta.startYear }}–{{ meta.endYear }}（{{ meta.yearCount }} 年 · 虚岁 {{ candles[0].age }}–{{ candles[candles.length - 1].age }}）</text>
          <text v-if="peak && trough" class="ov-stat">最高 {{ peak.year }} 年 {{ peak.close }} 分 · 最低 {{ trough.year }} 年 {{ trough.close }} 分</text>
        </view>
      </view>

      <!-- 图表 -->
      <view class="card">
        <view v-if="candles.length" class="chart-head">
          <text class="card-title">一生运势 K 线</text>
          <text v-if="switching" class="switch-hint">切换维度中…</text>
          <view v-else class="legend">
            <view class="lg-item"><text class="lg-swatch lg-up"></text><text class="lg-text">涨 · 比上一年好</text></view>
            <view class="lg-item"><text class="lg-swatch lg-down"></text><text class="lg-text">跌 · 比上一年差</text></view>
          </view>
        </view>

        <view class="chart-flex">
          <!-- 纵轴刻度（固定不随横轴滚动） -->
          <view class="y-axis">
            <text
              v-for="t in yTicks"
              :key="t"
              class="y-tick"
              :style="{ top: yPct(t) + '%' }"
            >{{ t }}</text>
          </view>

          <view class="chart-clip">
            <scroll-view
              class="chart-scroll"
              scroll-x
              :scroll-left="scrollLeftPx"
              :scroll-with-animation="true"
              :show-scrollbar="false"
            >
              <view class="chart-canvas" :style="{ width: canvasWidthRpx + 'rpx' }">
                <!-- 大运带（十年一段的宏观周期） -->
                <view class="band-row">
                  <view
                    v-for="(b, i) in renderBands"
                    :key="'b' + b.index"
                    :class="['band-cell', i % 2 === 1 && 'band-alt']"
                    :style="{ left: b.left, width: b.width }"
                  >{{ b.ganzhi }}</view>
                </view>

                <view class="plot">
                  <!-- 网格线 -->
                  <view
                    v-for="t in yTicks"
                    :key="'g' + t"
                    class="grid-line"
                    :style="{ top: yPct(t) + '%' }"
                  ></view>
                  <!-- 大运换柱（首段左沿即画布起点，不画） -->
                  <view
                    v-for="(b, bi) in renderBands"
                    :key="'s' + b.index"
                    v-show="bi > 0"
                    class="band-sep"
                    :style="{ left: b.left }"
                  ></view>
                  <!-- 蜡烛：影线为波动、实体为同比升降 -->
                  <view
                    v-for="c in renderCandles"
                    :key="c.year"
                    class="candle"
                    :style="{ left: c.left, width: c.slot }"
                  >
                    <view class="wick" :style="{ top: c.upTop, height: c.upH, background: c.color }"></view>
                    <view class="body" :style="{ top: c.bodyTop, height: c.bodyH, background: c.color }"></view>
                    <view class="wick" :style="{ top: c.lowTop, height: c.lowH, background: c.color }"></view>
                  </view>
                  <!-- 选中标记 -->
                  <view class="sel-line" :style="{ left: selLineLeft }"></view>
                  <view
                    v-for="c in renderCandles"
                    :key="'hit' + c.year"
                    :class="['hit', c.i === selIndex && 'hit-on']"
                    :style="{ left: c.left, width: c.slot }"
                    @tap="selectIndex(c.i)"
                  ></view>
                </view>

                <!-- 年份轴：与蜡烛同一滚动容器，保证对齐 -->
                <view class="axis-row">
                  <text
                    v-for="c in renderCandles"
                    :key="'y' + c.year"
                    v-show="c.showYear"
                    :class="['axis-year', c.isFirstYear && 'axis-year-start']"
                    :style="{ left: c.left, width: c.slot }"
                  >{{ c.year }}</text>
                </view>
              </view>
            </scroll-view>
          </view>
        </view>

        <!-- 年份滑杆：75 根蜡烛点不准，用滑杆定位 -->
        <view class="slider-row">
          <slider
            class="year-slider"
            :min="0"
            :max="maxIndex"
            :value="selIndex"
            :step="1"
            block-size="18"
            :activeColor="accentColor"
            backgroundColor="rgba(128,128,128,0.25)"
            @changing="onSlide"
            @change="onSlide"
          />
          <view class="slider-readout">
            <text class="ro-year">{{ sel.year }} 年</text>
            <text class="ro-age">虚岁 {{ sel.age }}</text>
            <text class="ro-gz">{{ sel.ganzhi }}年 · {{ sel.dayun ? sel.dayun + '运' : '童限' }}</text>
          </view>
        </view>
      </view>

      <!-- 选中年份详情 -->
      <view class="card">
        <view class="detail-head">
          <text class="card-title">{{ sel.year }} 年运势</text>
          <text :class="['detail-delta', sel.isUp ? 'delta-up' : 'delta-down']">
            {{ sel.isUp ? '▲' : '▼' }} {{ deltaText }}
          </text>
        </view>
        <view class="detail-grid">
          <view class="dt-cell"><text class="dt-label">开</text><text class="dt-value">{{ sel.open }}</text></view>
          <view class="dt-cell"><text class="dt-label">收</text><text class="dt-value">{{ sel.close }}</text></view>
          <view class="dt-cell"><text class="dt-label">高</text><text class="dt-value">{{ sel.high }}</text></view>
          <view class="dt-cell"><text class="dt-label">低</text><text class="dt-value">{{ sel.low }}</text></view>
          <view class="dt-cell"><text class="dt-label">关系波动</text><text class="dt-value">{{ sel.volatility }}</text></view>
          <view class="dt-cell"><text class="dt-label">关系修正</text><text class="dt-value">{{ sign(sel.relationAdj) }}{{ sel.relationAdj }}</text></view>
        </view>
        <view v-if="selRelations.length" class="rel-wrap">
          <text
            v-for="(r, i) in selRelations"
            :key="i"
            :class="['rel-chip', relClass(r)]"
          >{{ r }}</text>
        </view>
        <text v-else class="rel-empty">该年无合冲刑害</text>
        <view class="detail-actions">
          <text class="act-pill" @tap="toggleEventCard">{{ evCardOpen ? '收起' : '事件标注' }}</text>
          <text class="act-pill" @tap="loadYearAnnotation">解读这一年</text>
        </view>
      </view>

      <!-- 事件标注：可折叠卡片 -->
      <view v-if="evCardOpen" class="card">
        <view class="ev-head">
          <text class="card-title">事件标注</text>
          <text class="ev-count">{{ currentYearEvItems.length ? '本盘 ' + currentYearEvItems.length + ' 条' : '本盘暂无' }}</text>
        </view>
        <text class="ev-hint">记录这一年的真实事件（如：升职、结婚、搬家），用于验证K线准确率。</text>
        <view class="detail-actions">
          <text class="act-pill" @tap="toggleEventForm">
            {{ evFormOpen ? '收起' : '标注 ' + sel.year + ' 年' }}
          </text>
          <!-- 回测是只读动作，不该藏在收起态的表单里：光想看一眼命中率不该先填表 -->
          <text class="act-pill" @tap="runBacktest">{{ evBtLoading ? '回测中…' : '回测' }}</text>
        </view>

        <!-- 结果行紧贴按钮：事件攒到几十条时，放在列表底下等于"点了看不见"。 -->
        <text v-if="btLine" class="bt-line">{{ btLine }}</text>
        <text v-else-if="!bt" class="bt-line bt-line-idle">记录足够事件后，点击回测查看准确率。</text>

        <view v-if="evFormOpen" class="ev-form">
          <view class="ev-row">
            <text class="ev-label">命理年</text>
            <input
              v-model="evYear"
              class="ev-input ev-num"
              type="number"
              placeholder="如 2015"
              placeholder-class="reso-ph"
            />
          </view>
          <text class="ev-tip">💡 1-2月的事件通常记在上一年。</text>
          <view class="ev-row">
            <text class="ev-label">公历日期</text>
            <input
              v-model="evDate"
              class="ev-input"
              placeholder="可选，如 2015-03-08"
              placeholder-class="reso-ph"
            />
          </view>
          <view class="ev-row">
            <text class="ev-label">吉凶</text>
            <view class="ev-pills">
              <text
                v-for="p in EV_POLARITIES"
                :key="p.key"
                :class="['ev-pill', evPolarity === p.key && 'ev-pill-on']"
                @tap="evPolarity = p.key"
              >{{ p.label }}</text>
            </view>
          </view>
          <view class="ev-row">
            <text class="ev-label">领域</text>
            <view class="ev-pills">
              <text
                v-for="d in EV_DOMAINS"
                :key="d.key"
                :class="['ev-pill', evDomain === d.key && 'ev-pill-on']"
                @tap="evDomain = d.key"
              >{{ d.label }}</text>
            </view>
          </view>
          <view class="ev-row">
            <text class="ev-label">备注</text>
            <input
              v-model="evNote"
              class="ev-input"
              placeholder="发生了什么，如：升任部门经理"
              placeholder-class="reso-ph"
            />
          </view>
          <view class="detail-actions">
            <text class="act-pill" @tap="saveEvent">{{ evSaving ? '记录中…' : '记录' }}</text>
          </view>
          <text v-if="evMsg" class="ev-msg">{{ evMsg }}</text>
        </view>

        <view v-if="currentYearEvItems.length" class="ev-list">
          <view v-for="it in currentYearEvItems" :key="it.id" class="ev-item">
            <text class="ev-item-main">{{ it.ganzhiYear }} · {{ polarityLabel(it.polarity) }} · {{ domainLabel(it.domain) }}</text>
            <text class="ev-item-note">{{ it.note || it.eventDate || '—' }}</text>
            <text class="ev-del" @tap="removeEvent(it)">删</text>
          </view>
        </view>
      </view>

      <!-- K 线解读：全页唯一引入大模型的环节。分数仍由规则算出，这里只解释 -->
      <view class="card">
        <view class="anno-head">
          <text class="card-title">K 线解读</text>
          <text class="anno-scope">{{ annoScopeLabel }}</text>
        </view>
        <view v-if="annoLoading" class="anno-state">
          <text class="anno-hint">正在解读…</text>
        </view>
        <template v-else-if="anno && anno.ok">
          <text class="anno-text">{{ anno.text }}</text>
          <text class="anno-foot">AI 解读仅供参考</text>
          <!-- 反馈闭环：只写不读。沉淀下来的「哪张盘哪一年哪一维」才是校准的输入 -->
          <view class="fb-wrap">
            <text class="fb-label">这段解读准吗？</text>
            <view class="fb-row">
              <text
                v-for="opt in FB_OPTIONS"
                :key="opt.key"
                :class="['fb-pill', fbSent === opt.key && 'fb-pill-on']"
                @tap="sendFeedback(opt)"
              >{{ opt.label }}</text>
            </view>
            <text v-if="fbMsg" class="fb-msg">{{ fbMsg }}</text>
          </view>
        </template>
        <view v-else class="anno-state">
          <text class="anno-hint">{{ annoHint }}</text>
          <text v-if="annoIssue" class="anno-issue">{{ annoIssue }}</text>
        </view>
      </view>

      <!-- 合盘共振线：两条单盘曲线之上的只读叠加，不改上面任何分数 -->
      <view class="card">
        <view class="reso-head">
          <text class="card-title">合盘共振线</text>
          <text v-if="reso" class="reso-tag">{{ reso.base.relationKind || '—' }} · 基线 {{ reso.base.score }}</text>
        </view>

        <template v-if="!reso">
          <text class="reso-hint">输入对方出生时间，查看两人运势的同步情况。</text>
          <view class="reso-form">
            <input
              v-model="resoBirth"
              class="reso-input"
              placeholder="对方出生时间，如 1992-08-08 09:00"
              placeholder-class="reso-ph"
            />
            <view class="reso-row">
              <text
                v-for="g in ['男', '女']"
                :key="g"
                :class="['reso-g', resoGender === g && 'reso-g-on']"
                @tap="resoGender = g"
              >{{ g }}</text>
              <text class="act-pill reso-go" @tap="loadResonance">{{ resoLoading ? '计算中…' : '生成共振线' }}</text>
            </view>
            <text v-if="resoError" class="reso-err">{{ resoError }}</text>
          </view>
        </template>

        <template v-else>
          <view class="reso-sum">
            <text class="reso-sum-item">最喜 甲 {{ reso.favorA.mostFavored }} / 乙 {{ reso.favorB.mostFavored }}</text>
            <text class="reso-sum-item">均分 {{ reso.meta.meanScore }} · 最高 {{ reso.meta.peakYear }} · 最低 {{ reso.meta.troughYear }}（{{ reso.meta.yearCount }} 年）</text>
            <text class="reso-sum-item">夫妻宫 {{ reso.base.dayZhi.a }} / {{ reso.base.dayZhi.b }}{{ reso.base.dayZhi.relation ? ' · ' + reso.base.dayZhi.relation : '' }} · {{ reso.base.complement.aCovers || reso.base.complement.bCovers ? '五行可互补' : '五行互补弱' }}</text>
          </view>

          <scroll-view class="reso-scroll" scroll-x :show-scrollbar="false">
            <view class="reso-canvas" :style="{ width: resoWidth + 'rpx' }">
              <view class="reso-plot" :style="{ height: RESO_H + 'rpx' }">
                <view class="reso-mid"></view>
                <view
                  v-for="r in resoYears"
                  :key="r.year"
                  class="reso-col"
                  :style="{ left: r.left, width: r.width }"
                  @tap="pickResoYear(r.year)"
                >
                  <view class="reso-bar" :style="{ height: r.height, background: r.color }"></view>
                </view>
                <view class="reso-sel" :style="{ left: resoSelLeft }"></view>
              </view>
              <view class="reso-axis">
                <text
                  v-for="r in resoYears"
                  :key="'ry' + r.year"
                  v-show="r.showYear"
                  :class="['reso-axis-year', r.isFirst && 'reso-axis-first']"
                  :style="{ left: r.left, width: r.width }"
                >{{ r.year }}</text>
              </view>
            </view>
          </scroll-view>

          <view v-if="resoRow" class="reso-detail">
            <view class="reso-detail-head">
              <text class="reso-detail-year">{{ resoRow.year }} 年 · {{ resoRow.ganzhi }}</text>
              <text :class="['reso-detail-verdict', resoRow.resonance >= 58 ? 'rv-up' : resoRow.resonance < 42 ? 'rv-down' : 'rv-mid']">
                {{ resoRow.resonance }} · {{ resoRow.verdict }}
              </text>
            </view>
            <view class="detail-grid">
              <view class="dt-cell"><text class="dt-label">甲方</text><text class="dt-value">{{ resoRow.scoreA }}</text></view>
              <view class="dt-cell"><text class="dt-label">乙方</text><text class="dt-value">{{ resoRow.scoreB }}</text></view>
              <view class="dt-cell"><text class="dt-label">喜忌</text><text class="dt-value">{{ resoRow.align.label }}</text></view>
              <view class="dt-cell"><text class="dt-label">走向</text><text class="dt-value">{{ resoRow.sameDirection ? '同向' : '背离' }}</text></view>
              <view class="dt-cell"><text class="dt-label">夫妻宫</text><text class="dt-value">{{ resoRow.palace.a || '—' }} / {{ resoRow.palace.b || '—' }}</text></view>
              <view class="dt-cell"><text class="dt-label">同步</text><text class="dt-value">{{ sign(resoRow.terms.sync) }}{{ resoRow.terms.sync }}</text></view>
            </view>
            <text class="reso-note">{{ reso.meta.note }}</text>
          </view>

          <!-- 关系事件：共振权重**唯一**的校准数据源。
               单盘事件只能校准单盘打分口径；"这两人某年如何"才是共振分该对得上的真相。
               复用上面已填的对方生辰，故只在共振线生成后才出现。 -->
          <view class="pair-ev">
            <view class="pair-ev-head">
              <text class="pair-ev-title">关系事件</text>
              <text class="pair-ev-count">{{ pairEvItems.length ? '本对 ' + pairEvItems.length + ' 条' : '本对暂无' }}</text>
            </view>
            <text class="pair-ev-hint">记录这一年两人关系中的重要事件（如：结婚、吵架、和好）。</text>

            <view class="ev-row">
              <text class="ev-label">关系</text>
              <view class="ev-pills">
                <text
                  v-for="r in PAIR_RELATIONS"
                  :key="'rel' + r.key"
                  :class="['ev-pill', pairRelation === r.key && 'ev-pill-on']"
                  @tap="pairRelation = r.key"
                >{{ r.label }}</text>
              </view>
            </view>
            <view class="ev-row">
              <text class="ev-label">顺逆</text>
              <view class="ev-pills">
                <text
                  v-for="p in PAIR_POLARITIES"
                  :key="'pp' + p.key"
                  :class="['ev-pill', pairPolarity === p.key && 'ev-pill-on']"
                  @tap="pairPolarity = p.key"
                >{{ p.label }}</text>
              </view>
            </view>
            <view class="ev-row">
              <text class="ev-label">命理年</text>
              <input
                v-model="pairYear"
                class="ev-input ev-num"
                type="number"
                placeholder="如 2015"
                placeholder-class="reso-ph"
              />
            </view>
            <text class="ev-tip">💡 点击上方柱子可快速填入年份。</text>
            <view class="ev-row">
              <text class="ev-label">备注</text>
              <input
                v-model="pairNote"
                class="ev-input"
                placeholder="发生了什么，如：一起搬了家"
                placeholder-class="reso-ph"
              />
            </view>
            <view class="detail-actions">
              <text class="act-pill" @tap="savePairEvent">{{ pairSaving ? '记录中…' : '记录' }}</text>
              <text class="act-pill" @tap="runPairBt">{{ pairBtLoading ? '回测中…' : '回测' }}</text>
            </view>
            <text v-if="pairMsg" class="ev-msg">{{ pairMsg }}</text>

            <!-- 结果行紧贴按钮：事件攒多了时放在列表底下等于"点了看不见"。 -->
            <text v-if="pairBtLine" class="bt-line">{{ pairBtLine }}</text>
            <text v-else-if="!pairBt" class="bt-line bt-line-idle">记录足够事件后，点击回测查看准确率。</text>

            <view v-if="pairEvItems.length" class="ev-list">
              <view v-for="it in pairEvItems" :key="it.id" class="ev-item">
                <text class="ev-item-main">{{ it.ganzhiYear }} · {{ pairPolarityLabel(it.polarity) }} · {{ it.relation || '未标注' }}</text>
                <text class="ev-item-note">{{ it.note || it.eventDate || '—' }}</text>
                <text class="ev-del" @tap="removePairEvent(it)">删</text>
              </view>
            </view>
          </view>

          <view class="detail-actions">
            <text class="act-pill" @tap="resetResonance">换一个人</text>
          </view>
        </template>
      </view>

      <view class="foot-note">
        <text class="fn-text">{{ meta.note }}</text>
        <text class="fn-text">💡 使用提示：左右滑动查看不同年份，点击蜡烛查看详情，点击「解读这一年」获取AI分析。</text>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { useTheme } from '@/composables/useTheme'
import type { KlineAnnotation, KlineResonance } from '@/api'
import {
  getKline, getKlineAnnotation, getKlineEventStats, getKlineResonance, listKlineEvents,
  deleteKlineEvent, submitKlineEvent, submitKlineFeedback, runKlineBacktest,
  deleteKlinePairEvent, listKlinePairEvents, runKlinePairBacktest, submitKlinePairEvent,
  type KlineBacktest, type KlineCandle, type KlineData, type KlineDimension,
  type KlineDimensionOption, type KlineEventDomain, type KlineEventItem, type KlineEventStats,
  type KlinePairBacktest, type KlinePairEventItem, type KlinePolarity, type KlineRelation,
} from '@/api'

const { themeClass, isDark } = useTheme()

// 画布坐标域：固定 [0, 100]，不随维度或命盘自适应。
// 上下沿就取后端 `fortune_score.SCORE_MIN/SCORE_MAX`：`build_candle` 里 open/close 按它夹、
// high 取 min(SCORE_MAX, …)、low 取 max(SCORE_MIN, …)，四个价格值全落在 [0,100] 内，
// 故这个域下**任何一根蜡烛都不可能被裁切**，影线贴到 100 也仍在画布内。
// 曾是 [15, 85]：高分年份的影线一到 85 就被切平（2092 年前后成片红柱顶成一条直线），
// 看着像"分数到头了"，其实是画布到头了 —— 域比数据窄，图就在说谎。
// 固定域才能让「切维度」只换形状、不换刻度，两条曲线可以直接比高低。
const LO = 0
const HI = 100
// 每根蜡烛的横向占位（rpx）。18rpx 下实体约 14rpx，手机上可辨
const SLOT = 18
// 画布右沿留白：最后一根蜡烛显示完毕即止，不留多余空白。
const TAIL_RPX = 0
// 图表可视宽度（rpx）= 屏宽 − 页面左右内边距(24×2) − 卡片内边距(24×2) − 卡片边框(1×2) − 纵轴列(78)。
// 这几个数都写在 <style> 里，改样式必须同步这里。
// 曾按「两侧共 56rpx」估成 616，比真值大 42rpx：clamp 出的最大滚动位置永远差 42rpx 到终点，
// 滑杆/大运带跳到末段时最右边那格大运就被视口切掉一截（看着像"被挡"）。
const VIEWPORT_RPX = 750 - 24 * 2 - 24 * 2 - 2 - 78

const statusBarHeight = ref(20)
try {
  statusBarHeight.value = uni.getWindowInfo().statusBarHeight || 20
} catch {}

const loading = ref(true)
const switching = ref(false)
const error = ref('')
const data = ref<KlineData | null>(null)
const dimension = ref<KlineDimension>('comprehensive')
const selIndex = ref(0)
const scrollLeftPx = ref(0)

const birthTime = ref('')
const gender = ref('')
// 覆盖 10 步大运（后端按整段大运收尾）：按岁数截断会停在半个大运上，
// 末段那格窄到画不下干支，最右边那个大运的标签就被裁掉了。
const MAX_DAYUN = 10
let chartOpts: { sect: number; yunSect: number; longitude?: number; maxDayun: number } =
  { sect: 2, yunSect: 1, maxDayun: MAX_DAYUN }

const candles = computed<KlineCandle[]>(() => data.value?.candles || [])
const favor = computed(() => data.value?.favor || {
  dayMaster: '', dayMasterWuxing: '', strength: '', specialPattern: '',
  favor: {}, mostFavored: '', mostOpposed: '', ailment: '', ailmentNote: '',
})
const meta = computed(() => data.value?.meta || {
  startYear: null, endYear: null, yearCount: 0, maxAge: 0,
  dimension: 'comprehensive' as KlineDimension, dimensionLabel: '', dimensionNote: '',
  dimensionEmphasis: {}, availableDimensions: [] as KlineDimensionOption[],
  kScore: 0, weightDayun: 0, weightLiunian: 0, weightLiuyue: 0, note: '',
})
const dimensions = computed<KlineDimensionOption[]>(() => meta.value.availableDimensions || [])
const maxIndex = computed(() => Math.max(candles.value.length - 1, 0))
const canvasWidthRpx = computed(() => candles.value.length * SLOT + TAIL_RPX)

// 涨红跌绿（国内习惯）。canvas 之外的 view 也走同一套色，
// 故这里给具体色值而不是 CSS 变量：影线/实体要在两套主题下都够对比度。
const UP_LIGHT = '#B8483C'
const DOWN_LIGHT = '#2E7D6E'
const UP_DARK = '#E0655A'
const DOWN_DARK = '#46B79D'
const upColor = computed(() => (isDark.value ? UP_DARK : UP_LIGHT))
const downColor = computed(() => (isDark.value ? DOWN_DARK : DOWN_LIGHT))
const accentColor = computed(() => (isDark.value ? UP_DARK : UP_LIGHT))

// 刻度与坐标域同为整十分档，两端都标：后端分数被夹在 [0,100]，
// 标出 100 才能一眼看出某根蜡烛是"满分"还是"被画布削平"，标出 0 才是真的到底。
const yTicks = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
const yPct = (v: number) => (1 - (v - LO) / (HI - LO)) * 100
const sign = (v: number) => (v > 0 ? '+' : '')

const renderCandles = computed(() => {
  const list = candles.value
  const first = list[0]?.year ?? 0
  const slotPct = list.length ? 100 / list.length : 0
  return list.map((c, i) => {
    const up = Math.max(c.open, c.close)
    const down = Math.min(c.open, c.close)
    const top = yPct(up)
    const bottom = yPct(down)
    const color = c.isUp ? upColor.value : downColor.value
    return {
      i,
      year: c.year,
      // 每年都标会糊成一片，十年一标
      showYear: (c.year - first) % 10 === 0,
      // 首年居中的话左半会溢出画布、被滚动容器裁掉，故首个标签改左对齐
      isFirstYear: i === 0,
      left: i * SLOT + 'rpx',
      slot: SLOT + 'rpx',
      // 实体至少留 1.2% 高度，否则"开收相等"的平年会在图里消失
      bodyTop: top + '%',
      bodyH: Math.max(bottom - top, 1.2) + '%',
      upTop: yPct(c.high) + '%',
      upH: Math.max(top - yPct(c.high), 0) + '%',
      lowTop: bottom + '%',
      lowH: Math.max(yPct(c.low) - bottom, 0) + '%',
      color,
    }
  })
})

const renderBands = computed(() => {
  const list = candles.value
  if (!list.length) return []
  const first = list[0].year
  const last = list[list.length - 1].year
  return (data.value?.dayunBands || [])
    .map((b) => {
      const s = Math.max(b.startYear, first)
      const e = Math.min(b.endYear, last)
      return { ...b, firstYear: s, n: e - s + 1 }
    })
    .filter((b) => b.n > 0)
    .map((b) => ({ ...b, left: (b.firstYear - first) * SLOT + 'rpx', width: b.n * SLOT + 'rpx' }))
})

const sel = computed<KlineCandle>(() => candles.value[selIndex.value] || ({} as KlineCandle))
const selRelations = computed<string[]>(() => sel.value.relations || [])
const selLineLeft = computed(() => selIndex.value * SLOT + SLOT / 2 + 'rpx')
const deltaText = computed(() => {
  const d = Math.round(((sel.value.close || 0) - (sel.value.open || 0)) * 10) / 10
  return (d > 0 ? '+' : '') + d
})

const peak = computed(() => {
  const list = candles.value
  if (!list.length) return null
  return list.reduce((a, b) => (b.close > a.close ? b : a))
})
const trough = computed(() => {
  const list = candles.value
  if (!list.length) return null
  return list.reduce((a, b) => (b.close < a.close ? b : a))
})

/** 关系标签着色：冲/刑/害/破 主变动，合/会 主和顺 */
function relClass(rel: string): string {
  if (rel.includes('冲') || rel.includes('反吟') || rel.includes('天克地冲')) return 'rel-chong'
  if (rel.includes('刑')) return 'rel-xing'
  if (rel.includes('害') || rel.includes('破')) return 'rel-hai'
  if (rel.includes('合') || rel.includes('会')) return 'rel-he'
  if (rel.includes('伏吟')) return 'rel-fu'
  return ''
}

/**
 * 滑杆定位后把图表滚到该年居中。
 * 用受控 scroll-left 而非 scroll-into-view：后者只对齐左边缘，看不到"前后各几年"的走势。
 */
function centerOn(index: number) {
  let winW = 375
  try {
    winW = uni.getWindowInfo().windowWidth || 375
  } catch {}
  const rpx2px = winW / 750
  const viewportRpx = VIEWPORT_RPX
  const target = index * SLOT + SLOT / 2 - viewportRpx / 2
  const maxScroll = Math.max(canvasWidthRpx.value - viewportRpx, 0)
  scrollLeftPx.value = Math.round(Math.max(0, Math.min(target, maxScroll)) * rpx2px)
}

function onSlide(e: any) {
  const next = Number(e?.detail?.value ?? 0)
  if (next === selIndex.value) return
  selIndex.value = next
  centerOn(next)
}

function selectIndex(i: number) {
  selIndex.value = i
  centerOn(i)
}

function jumpToBand(b: { firstYear: number; index: number }) {
  const idx = candles.value.findIndex((c) => c.year === b.firstYear)
  if (idx >= 0) selectIndex(idx)
}

function switchDimension(key: KlineDimension) {
  if (key === dimension.value) return
  dimension.value = key
  load()
}

function load() {
  if (!birthTime.value || !gender.value) {
    loading.value = false
    return
  }
  // 切维度时同一条时间轴，保留选中年份，避免每次都跳回起点
  const keepYear = candles.value[selIndex.value]?.year
  error.value = ''
  if (data.value) switching.value = true
  else loading.value = true
  getKline(birthTime.value, gender.value, { ...chartOpts, dimension: dimension.value })
    .then((res) => {
      data.value = res
      // loading 期间模板不渲染 chart-flex，靠数据先落地再定位，避免宽度为 0 时算错滚动位置
      const idx = keepYear ? res.candles.findIndex((c) => c.year === keepYear) : 0
      selIndex.value = idx >= 0 ? idx : 0
      centerOn(selIndex.value)
      // 批注跟着维度和曲线走：换了维度就是另一条曲线，旧的解读不能再留着
      loadAnnotation('overview')
      // 事件表与维度无关，一张盘只拉一次
      if (!evLoaded) {
        evLoaded = true
        loadEvents()
      }
      // 共振线也吃维度（双方喜忌都随维度变），已生成过就得跟着重算
      if (reso.value && resoBirth.value.trim()) loadResonance()
    })
    .catch((e: Error) => {
      error.value = e?.message || 'K 线计算失败'
      data.value = null
    })
    .finally(() => {
      loading.value = false
      switching.value = false
    })
}

// ---- K 线解读（全页唯一引入大模型的环节；分数与它无关）----
// 粒度取「概览先给 + 年份按需」：进页面就给一段全期解读，某一年要细看再点一下。
// 不按年预生成（75 年 = 75 次调用）——那是预先花钱买没人看的内容。
const anno = ref<KlineAnnotation | null>(null)
const annoLoading = ref(false)
const annoError = ref('')

const annoScopeLabel = computed(() =>
  anno.value?.scope === 'year' && anno.value.year ? `${anno.value.year} 年` : '全期概览'
)
const annoHint = computed(() =>
  annoError.value || '这段解读未通过事实校验，已隐藏'
)
const annoIssue = computed(() => anno.value?.issues?.[0] || '')

async function loadAnnotation(scope: 'overview' | 'year', year?: number) {
  if (!birthTime.value || !gender.value) return
  annoLoading.value = true
  annoError.value = ''
  // 换了批注就重置反馈态：上一段的「已记录」不该跟着新的一段落下来
  fbSent.value = ''
  fbMsg.value = ''
  try {
    anno.value = await getKlineAnnotation(birthTime.value, gender.value, {
      ...chartOpts,
      dimension: dimension.value,
      scope,
      ...(year ? { year } : {}),
    })
  } catch (e: any) {
    annoError.value = e?.message || '解读暂不可用'
    anno.value = null
  } finally {
    annoLoading.value = false
  }
}

function loadYearAnnotation() {
  loadAnnotation('year', sel.value.year)
}

// ---- 反馈闭环（只写，不影响任何分数）----
// 三档而不是五档：手机上一行放得下，且「准 / 说不准 / 不准」正好对上
// accurate 的 true / null / false —— 星数只是它的量化侧面。
const FB_OPTIONS = [
  { key: 'good', label: '准', rating: 5, accurate: true as boolean | null },
  { key: 'unsure', label: '说不准', rating: 3, accurate: null as boolean | null },
  { key: 'bad', label: '不准', rating: 2, accurate: false as boolean | null },
]
const fbSent = ref('')
const fbMsg = ref('')

async function sendFeedback(opt: (typeof FB_OPTIONS)[number]) {
  if (fbSent.value || !anno.value?.ok) return
  const a = anno.value
  try {
    await submitKlineFeedback({
      birthTime: birthTime.value,
      gender: gender.value,
      dimension: dimension.value,
      scope: a.scope,
      ...(a.scope === 'year' && a.year ? { year: a.year } : {}),
      ...(a.anchorYear ? { anchorYear: a.anchorYear } : {}),
      rating: opt.rating,
      accurate: opt.accurate,
      // 存批注指纹而不是全文：全文是模型产出、会随口径漂移，指纹只用于事后定位
      snapshot: { scope: a.scope, year: a.year ?? null, textLength: a.text.length, factsOk: a.factsOk },
    })
    fbSent.value = opt.key
    fbMsg.value = '已记录，谢谢'
  } catch (e: any) {
    fbMsg.value = e?.message || '反馈没记上，稍后再试'
  }
}

// ---- 事件标注（回测的真相面；只写不读，不改任何分数）----
// 与上面的"反馈"分工明确：反馈是主观认可度，事件是客观发生的事实。回测只吃事件。
// 年份默认跟着当前选中的那一年走 —— 看着哪年想起来什么，就地记下来。
const EV_POLARITIES: { key: KlinePolarity; label: string }[] = [
  { key: 1, label: '吉' },
  { key: 0, label: '平' },
  { key: -1, label: '凶' },
]
const EV_DOMAINS: { key: KlineEventDomain; label: string }[] = [
  { key: 'general', label: '综合' },
  { key: 'career', label: '事业' },
  { key: 'wealth', label: '财运' },
  { key: 'love', label: '感情' },
  { key: 'health', label: '健康' },
  { key: 'study', label: '学业' },
]
const EV_MAX_ITEMS = 200

const evFormOpen = ref(false)
const evCardOpen = ref(false)
const evYear = ref('')
const evDate = ref('')
const evPolarity = ref<KlinePolarity>(1)
const evDomain = ref<KlineEventDomain>('general')
const currentYearEvItems = computed(() => {
  const targetYear = Number(sel.value?.year)
  if (!Number.isInteger(targetYear)) return evItems.value
  return evItems.value.filter((it) => Number(it.ganzhiYear) === targetYear)
})
const evNote = ref('')
const evMsg = ref('')
const evSaving = ref(false)
const evItems = ref<KlineEventItem[]>([])
const evStats = ref<KlineEventStats | null>(null)
const bt = ref<KlineBacktest | null>(null)
const evBtLoading = ref(false)
let evLoaded = false

// 回测下限与后端默认一致；低于它后端会给 ok=false，前端照实显示。
// 单盘/合盘共用同一个下限 —— 两处各写一个数迟早会漂。
const BT_MIN_SAMPLES = 20

const polarityLabel = (p: number) => EV_POLARITIES.find((x) => x.key === p)?.label || '—'
const domainLabel = (d: string) => EV_DOMAINS.find((x) => x.key === d)?.label || d

/**
 * 回测结果一行的文案。**单盘与合盘共用**：这两个数字将来要拿来做同一件事
 * （校准打分口径），两处各写一份迟早出现"同一个命中率两种读法"。
 *
 * 硬规则（都不是排版偏好，是读法问题）：
 * - 必须连随机基线一起给：三分类随机猜也有约 1/3，事件吉凶本来就偏的话
 *   "全猜多数类"还能更高；lift 为负就是**还不如瞎猜**。
 * - 样本不足时只报事实、不给百分比 —— 3 条里的 66.7% 会被人当结论用。
 * - 窗口外的年份永远回测不了（阈值固定按全期分位切，不随事件伸缩）：
 *   刚录完就显示"没有可用事件"会让人以为没存上，故要把原因和区间说出来。
 */
function formatBtLine(
  b: KlineBacktest | KlinePairBacktest,
  noun: '盘' | '对',
  scope: string
): string {
  const s = b.summary
  const win = b.spanFrom != null && b.spanTo != null ? `${b.spanFrom}–${b.spanTo}` : ''
  const un = b.events?.unmatched || 0
  const outside = un ? `窗口外 ${un} 条${win ? `（回测区间 ${win}）` : ''}` : ''
  if (!s?.samples) {
    if (outside) return `${outside}，区间内暂无可回测事件。回测固定按 1–${b.ageSpan} 虚岁取全期阈值。`
    return `本${noun}还没有可用于回测的事件。`
  }
  if (!s.ok) {
    return [`已攒 ${s.samples}/${b.minSamples} 条（${scope}）—— 还没到能谈命中率的量`, outside]
      .filter(Boolean).join(' · ')
  }
  const pct = (v: number | null | undefined) => (v == null ? '—' : (v * 100).toFixed(1) + '%')
  const lift = s.liftStrict == null ? '—' : (s.liftStrict > 0 ? '+' : '') + (s.liftStrict * 100).toFixed(1) + 'pp'
  const bad = ('termDiagnostics' in b ? b.termDiagnostics || [] : [])
    .filter((d) => d.signOk === false).map((d) => d.term)
  return [
    `命中 ${s.hits}/${s.decided}（${pct(s.hitRateStrict)}）`,
    `随机 ${pct(s.randomBaselineStrict)}`,
    `lift ${lift}`,
    s.significant ? '显著' : '不显著',
    outside,
    bad.length ? `方向反了：${bad.join('/')}` : '',
  ].filter(Boolean).join(' · ')
}

const btLine = computed(() =>
  bt.value ? formatBtLine(bt.value, '盘', `${bt.value.charts} 张盘`) : ''
)

/**
 * 跑一次单盘回测。`dimension` 传 `auto`：**按事件各自的领域选维度** ——
 * 拿综合维度去评判一条"那年离婚了"的标注，问的其实是另一个问题。
 * 也正因如此，它不是页面当前选中的那个维度，切维度不需要重跑。
 */
async function runBacktest() {
  if (evBtLoading.value || !birthTime.value || !gender.value) return
  evBtLoading.value = true
  try {
    bt.value = await runKlineBacktest({
      birthTime: birthTime.value,
      gender: gender.value,
      dimension: 'auto',
      minSamples: BT_MIN_SAMPLES,
    })
  } catch (e: any) {
    evMsg.value = e?.message || '回测失败'
  } finally {
    evBtLoading.value = false
  }
}

function toggleEventCard() {
  evCardOpen.value = !evCardOpen.value
  if (!evCardOpen.value) {
    evFormOpen.value = false
    return
  }
  evFormOpen.value = false
  evYear.value = String(sel.value.year)
  evDate.value = ''
  evMsg.value = ''
  loadEventStats()
}

function toggleEventForm() {
  evFormOpen.value = !evFormOpen.value
  if (!evFormOpen.value) return
  // 每次展开都回到当前选中的那一年：滑杆挪到别处再点开，预期是标那一年
  evYear.value = String(sel.value.year)
  evDate.value = ''
  evMsg.value = ''
  loadEventStats()
}

async function loadEvents() {
  if (!birthTime.value || !gender.value) return
  try {
    const res = await listKlineEvents({
      birthTime: birthTime.value,
      gender: gender.value,
      limit: EV_MAX_ITEMS,
    })
    evItems.value = res.items || []
  } catch {
    // 事件表拉不到不该把整页拖下水：K 线本身与它无关
  }
}

async function loadEventStats() {
  try {
    evStats.value = await getKlineEventStats()
  } catch {
    evStats.value = null
  }
}

async function saveEvent() {
  if (evSaving.value) return
  const year = Number(evYear.value)
  const date = evDate.value.trim()
  if (!date && !(Number.isInteger(year) && year > 1000)) {
    evMsg.value = '填一个命理年，或直接填公历日期'
    return
  }
  evSaving.value = true
  evMsg.value = ''
  try {
    // 两个来源都给时交给后端交叉校验（立春换岁），本地不重复推一遍免得两处口径打架
    const res = await submitKlineEvent({
      birthTime: birthTime.value,
      gender: gender.value,
      sect: chartOpts.sect,
      yunSect: chartOpts.yunSect,
      ...(chartOpts.longitude ? { longitude: chartOpts.longitude } : {}),
      ...(date ? { eventDate: date } : { ganzhiYear: year }),
      polarity: evPolarity.value,
      domain: evDomain.value,
      note: evNote.value.trim(),
      source: '小程序',
    })
    evMsg.value = `已记录：${res.ganzhiYear} 年`
    evNote.value = ''
    await loadEvents()
    loadEventStats()
    // 刚录完正是这个数字最该动的时候，顺手重算一行
    runBacktest()
  } catch (e: any) {
    evMsg.value = e?.message || '没记上，稍后再试'
  } finally {
    evSaving.value = false
  }
}

async function removeEvent(it: KlineEventItem) {
  try {
    await deleteKlineEvent(it.id)
    evItems.value = evItems.value.filter((x) => x.id !== it.id)
    loadEventStats()
    if (evMsg.value) evMsg.value = ''
    if (bt.value) runBacktest()
  } catch (e: any) {
    evMsg.value = e?.message || '删除失败'
  }
}

// ---- 合盘共振线（只读叠加，不改上面任何分数）----
const RESO_SLOT = 18
const RESO_H = 200

const reso = ref<KlineResonance | null>(null)
const resoBirth = ref('')
const resoGender = ref('女')
const resoLoading = ref(false)
const resoError = ref('')
const resoYear = ref<number | null>(null)

const resoWidth = computed(() =>
  reso.value ? reso.value.years.length * RESO_SLOT + 12 : 0
)
const resoYears = computed(() =>
  (reso.value?.years || []).map((r, i) => ({
    year: r.year,
    resonance: r.resonance,
    left: i * RESO_SLOT + 2 + 'rpx',
    width: RESO_SLOT - 4 + 'rpx',
    height: Math.max(2, Math.round((r.resonance / 100) * RESO_H)) + 'rpx',
    color: resoColor(r.verdict),
    // 年份轴每 5 年一个 + 首年，跟主图同一套稀疏策略
    showYear: i === 0 || r.year % 5 === 0,
    isFirst: i === 0,
  }))
)
const resoSelIndex = computed(() =>
  reso.value ? reso.value.years.findIndex((r) => r.year === resoYear.value) : -1
)
const resoSelLeft = computed(() =>
  resoSelIndex.value < 0 ? '0rpx' : resoSelIndex.value * RESO_SLOT + RESO_SLOT / 2 + 'rpx'
)
const resoRow = computed(() =>
  reso.value?.years.find((r) => r.year === resoYear.value) || null
)

/* ---- 关系事件（共振权重唯一的校准数据源）---- */
// 默认「未标注」而不是猜一个关系类型：关系类型只是复盘切片维度，
// 猜错会让「按关系类型分组看命中率」那张表从第一天就是脏的。
const PAIR_RELATIONS: { key: KlineRelation | ''; label: string }[] = [
  { key: '', label: '未标注' },
  { key: '夫妻', label: '夫妻' },
  { key: '恋人', label: '恋人' },
  { key: '亲子', label: '亲子' },
  { key: '同事', label: '同事' },
  { key: '朋友', label: '朋友' },
  { key: '合作', label: '合作' },
  { key: '其他', label: '其他' },
]
// 顺/逆 而不是 吉/凶：这里判的是关系本身，不是某一方的个人运势
const PAIR_POLARITIES: { key: KlinePolarity; label: string }[] = [
  { key: 1, label: '顺' },
  { key: 0, label: '平' },
  { key: -1, label: '逆' },
]
// 回测下限与后端默认一致，见 BT_MIN_SAMPLES（单盘/合盘共用，别在这再写一个）
const PAIR_MAX_ITEMS = 200

const pairRelation = ref<KlineRelation | ''>('')
const pairPolarity = ref<KlinePolarity>(1)
const pairYear = ref('')
const pairNote = ref('')
const pairMsg = ref('')
const pairSaving = ref(false)
const pairEvItems = ref<KlinePairEventItem[]>([])
const pairBt = ref<KlinePairBacktest | null>(null)
const pairBtLoading = ref(false)

const pairPolarityLabel = (p: number) =>
  PAIR_POLARITIES.find((x) => x.key === p)?.label || '—'

const pairBtLine = computed(() =>
  pairBt.value ? formatBtLine(pairBt.value, '对', `${pairBt.value.pairs} 对`) : ''
)

/** 点柱子既选年也把年份带进事件表单：看着哪年想起来什么，就地记下来 */
function pickResoYear(year: number) {
  resoYear.value = year
  pairYear.value = String(year)
}

async function loadPairEvents() {
  const bt = resoBirth.value.trim()
  if (!birthTime.value || !gender.value || !bt) return
  try {
    const res = await listKlinePairEvents({
      birthTimeA: birthTime.value,
      genderA: gender.value,
      birthTimeB: bt,
      genderB: resoGender.value,
      limit: PAIR_MAX_ITEMS,
    })
    pairEvItems.value = res.items || []
  } catch {
    // 关系事件拉不到不该把共振线拖下水
  }
}

async function savePairEvent() {
  if (pairSaving.value) return
  const bt = resoBirth.value.trim()
  const year = Number(pairYear.value)
  if (!bt) {
    pairMsg.value = '请先填对方生辰'
    return
  }
  if (!Number.isInteger(year) || year <= 1000) {
    pairMsg.value = '填一个命理年，如 2015'
    return
  }
  pairSaving.value = true
  pairMsg.value = ''
  try {
    const res = await submitKlinePairEvent({
      birthTimeA: birthTime.value,
      genderA: gender.value,
      birthTimeB: bt,
      genderB: resoGender.value,
      sect: chartOpts.sect,
      yunSect: chartOpts.yunSect,
      ganzhiYear: year,
      polarity: pairPolarity.value,
      relation: pairRelation.value,
      note: pairNote.value.trim(),
      source: '小程序',
    })
    pairMsg.value = `已记录：${res.ganzhiYear} 年`
    pairNote.value = ''
    await loadPairEvents()
    // 刚录完正是这个数字最该动的时候，顺手重算一行
    runPairBt()
  } catch (e: any) {
    pairMsg.value = e?.message || '没记上，稍后再试'
  } finally {
    pairSaving.value = false
  }
}

async function removePairEvent(it: KlinePairEventItem) {
  try {
    await deleteKlinePairEvent(it.id)
    pairEvItems.value = pairEvItems.value.filter((x) => x.id !== it.id)
    if (pairMsg.value) pairMsg.value = ''
    if (pairBt.value) runPairBt()
  } catch (e: any) {
    pairMsg.value = e?.message || '删除失败'
  }
}

/**
 * 跑合盘回测。按「这一对」过滤 —— 一个人可能有好几段关系，
 * 把别人那条关系的分数混进来算命中率就是自己骗自己。
 */
async function runPairBt() {
  const bt = resoBirth.value.trim()
  if (pairBtLoading.value || !birthTime.value || !gender.value || !bt) return
  pairBtLoading.value = true
  try {
    pairBt.value = await runKlinePairBacktest({
      birthTimeA: birthTime.value,
      genderA: gender.value,
      birthTimeB: bt,
      genderB: resoGender.value,
      dimension: dimension.value,
      minSamples: BT_MIN_SAMPLES,
    })
  } catch (e: any) {
    pairMsg.value = e?.message || '回测失败'
  } finally {
    pairBtLoading.value = false
  }
}

function resetPairEvents() {
  pairEvItems.value = []
  pairBt.value = null
  pairMsg.value = ''
  pairNote.value = ''
  pairYear.value = ''
}

/** 顺为红、逆为绿（与主图涨跌同色系），平稳走中性灰 */
function resoColor(verdict: string) {
  if (verdict === '强共振' || verdict === '偏顺') return upColor.value
  if (verdict === '偏逆' || verdict === '背离') return downColor.value
  return 'rgba(128,128,128,0.55)'
}

async function loadResonance() {
  const bt = resoBirth.value.trim()
  if (!birthTime.value || !gender.value) return
  if (!bt) {
    resoError.value = '请填写对方的出生时间'
    return
  }
  resoLoading.value = true
  resoError.value = ''
  try {
    const res = await getKlineResonance(
      { birthTime: birthTime.value, gender: gender.value },
      { birthTime: bt, gender: resoGender.value },
      { ...chartOpts, dimension: dimension.value }
    )
    reso.value = res
    // 关系事件是按「这一对」存的，换人就整个换一批 —— 必须先清再落年份，
    // 否则 resetPairEvents 会把刚填好的年份又抹掉。
    resetPairEvents()
    // 默认落到最高的一年：那是用户最想看的那一格，也是事件表单的默认年
    const peak = res.meta.peakYear ?? res.years[0]?.year ?? null
    resoYear.value = peak
    if (peak != null) pairYear.value = String(peak)
    loadPairEvents()
  } catch (e: any) {
    resoError.value = e?.message || '共振线计算失败'
    reso.value = null
  } finally {
    resoLoading.value = false
  }
}

function resetResonance() {
  reso.value = null
  resoYear.value = null
  resoError.value = ''
  resetPairEvents()
}

function goBack() {
  const pages = getCurrentPages()
  if (pages.length > 1) uni.navigateBack()
  else uni.switchTab({ url: '/pages/xianzhi/index' })
}

onLoad((options: any) => {
  const decode = (v?: string) => {
    if (!v) return ''
    try { return decodeURIComponent(v) } catch { return v }
  }
  birthTime.value = decode(options.birth_time)
  gender.value = decode(options.gender)
  if (!birthTime.value || !gender.value) {
    loading.value = false
    return
  }
  chartOpts = {
    sect: Number(options.sect || 2) || 2,
    yunSect: Number(options.yun_sect || 1) || 1,
    longitude: Number(options.longitude || 0) || undefined,
    maxDayun: MAX_DAYUN,
  }
  load()
})
</script>

<style lang="scss" scoped>
.display-font { font-family: $font-family-display; }

/* 图表三段行高必须同源：纵轴靠 margin-top 对齐绘图区、滚动容器高度是三段之和。
   曾因三处各写一个数导致「纵轴刻度比网格线高 34rpx」+「年份轴被裁 14rpx」。 */
$chart-band-row: 34rpx;   /* 大运干支标签行 */
/* 绘图区高度=纵向分辨率：坐标域固定 [0,100]，440rpx 下 1 分只有 2.2px，
   一档 20 分的年际差也就 44px，蜡烛挤成一排小方块。
   580rpx 让 1 分 = 2.9px（+32%），整卡 380px 仍在一屏之内；
   再往上（720rpx=360px）卡片就占掉大半屏，纵轴反而要来回扫。 */
$chart-plot: 580rpx;      /* 绘图区 */
$chart-axis-row: 34rpx;   /* 年份轴 */

.page-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: $color-paper;
}
.navbar {
  flex-shrink: 0;
  background: $color-paper-warm;
  border-bottom: 1rpx solid $color-border;
}
.navbar-inner {
  display: flex;
  align-items: center;
  height: 88rpx;
  padding: 0 24rpx;
  position: relative;
}
.nav-back { font-size: 30rpx; color: $color-ink-light; padding: 8rpx 12rpx; position: relative; z-index: 2; }
.nav-ghost { opacity: 0; position: relative; z-index: 2; }
.nav-title {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  font-size: 34rpx;
  font-weight: 600;
  color: $color-ink;
  letter-spacing: 6rpx;
  white-space: nowrap;
  z-index: 1;
}

.dim-bar {
  flex-shrink: 0;
  background: $color-paper-warm;
  border-bottom: 1rpx solid $color-border;
  white-space: nowrap;
}
/* 维度不够宽时整组居中；min-width:max-content 是给将来维度变多留的后路 ——
   纯 center 在内容超宽时会把左侧挤出滚动区（滚不回去），取满内容宽后 center 自动失效。 */
.dim-row { display: flex; justify-content: center; min-width: max-content; padding: 0 12rpx; }
.dim-btn {
  flex-shrink: 0;
  padding: 14rpx 26rpx 12rpx;
  font-size: 27rpx;
  color: $color-ink-light;
  position: relative;
}
.dim-btn.dim-active { color: $color-vermilion; font-weight: 600; }
.dim-btn.dim-active::after {
  content: '';
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  bottom: 0;
  width: 40rpx;
  height: 5rpx;
  border-radius: 3rpx;
  background: $color-vermilion;
}

.page-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 80rpx 40rpx;
  color: $color-ink-light;
  font-size: 28rpx;
  text-align: center;
}
/* height:0 + flex:1 + min-height:0：小程序 flex 子项默认 min-height:auto，
   会被内容撑到全高导致内部 scroll-y 无余量（见 chart-detail 同款注释）。 */
.page-body { flex: 1; height: 0; min-height: 0; padding: 20rpx 24rpx 40rpx; box-sizing: border-box; }

.card {
  background: $color-paper-dark;
  border: 1rpx solid $color-border;
  border-radius: $radius-lg;
  padding: 24rpx;
  margin-bottom: 24rpx;
}
.card-title { font-size: 28rpx; font-weight: 600; color: $color-ink; }

.ov-grid { display: flex; flex-wrap: wrap; }
.ov-cell { width: 50%; padding: 8rpx 0; display: flex; align-items: baseline; }
.ov-label { font-size: 28rpx; color: $color-ink-light; margin-right: 12rpx; font-weight: 500; }
.ov-value { font-size: 32rpx; color: $color-ink; font-weight: 600; }
.ov-note { display: block; margin-top: 14rpx; font-size: 27rpx; color: $color-ink-light; line-height: 1.6; }
/* 病药说明是「最喜/最忌」的依据，比维度说明更需要被读到，故用正文色 */
.ov-ailment { color: $color-ink; line-height: 1.7; font-weight: 500; }
.ov-stats { margin-top: 14rpx; padding-top: 14rpx; border-top: 1rpx solid $color-border-light; }
.ov-stat { display: block; font-size: 26rpx; color: $color-ink-light; line-height: 1.8; }

.chart-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 18rpx; }
.switch-hint { font-size: 25rpx; color: $color-ink-light; }
.legend { display: flex; }
.lg-item { display: flex; align-items: center; margin-left: 18rpx; }
.lg-swatch { width: 18rpx; height: 18rpx; border-radius: 3rpx; margin-right: 8rpx; }
.lg-up { background: #B8483C; }
.lg-down { background: #2E7D6E; }
.lg-text { font-size: 25rpx; color: $color-ink-light; font-weight: 500; }

.chart-flex { display: flex; align-items: flex-start; }
.y-axis {
  width: 78rpx;
  height: $chart-plot;
  /* 对齐绘图区：绘图区前面隔了一行大运标签 */
  margin-top: $chart-band-row;
  position: relative;
  flex-shrink: 0;
}
.y-tick {
  position: absolute;
  right: 10rpx;
  transform: translateY(-50%);
  font-size: 20rpx;
  color: $color-ink-lightest;
}
/* 视口裁切交给这一层。mp-weixin 的 scroll-view 会把已经滚过右侧的内容画到自己的盒子之外
   （实测：画布内容越过卡片右内边距、一直到卡片边框才断），视觉上就是"最右边那段被挡住"。
   外框给死宽度 + overflow:hidden，内容就只出现在真正的视口里；
   min-width:0 不能省 —— flex 子项默认 min-width:auto（= 内容最小宽），画布那 1300+rpx 会把这层顶开。 */
.chart-clip { flex: 1; min-width: 0; overflow: hidden; }
.chart-scroll { width: 100%; height: $chart-band-row + $chart-plot + $chart-axis-row; }
.chart-canvas { position: relative; }

.band-row { height: $chart-band-row; position: relative; }
.band-cell {
  position: absolute;
  top: 0;
  height: $chart-band-row;
  line-height: $chart-band-row;
  text-align: center;
  font-size: 21rpx;
  color: $color-ink-lighter;
  overflow: hidden;
}
.band-alt { background: $color-border-light; border-radius: 6rpx; }

/* 绘图区自己兜住越界内容：坐标域 [0,100] 已保证蜡烛不出界，这层是防后端分数万一越界时
   影线画到卡片标题/大运带上去（.plot 不裁剪的话，越界影线会直接盖住上面的字，
   看起来比"被削平"更像坏了）。 */
.plot { height: $chart-plot; position: relative; overflow: hidden; }
.grid-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 1rpx;
  background: $color-border-light;
}
.band-sep {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1rpx;
  border-left: 1rpx dashed $color-border;
}
.candle { position: absolute; top: 0; height: 100%; }
.wick {
  position: absolute;
  left: 50%;
  width: 2rpx;
  margin-left: -1rpx;
  border-radius: 2rpx;
}
.body {
  position: absolute;
  left: 2rpx;
  right: 2rpx;
  border-radius: 2rpx;
}
.sel-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2rpx;
  margin-left: -1rpx;
  background: $color-vermilion;
  opacity: 0.75;
}
/* 触控命中层：蜡烛本身太细，独立一层撑满 slot 高度 */
.hit { position: absolute; top: 0; height: 100%; }
.hit-on { background: rgba(184, 72, 60, 0.07); }

.axis-row { height: $chart-axis-row; position: relative; }
.axis-year {
  position: absolute;
  top: 4rpx;
  font-size: 24rpx;
  color: $color-ink-light;
  text-align: center;
  font-weight: 500;
}
.axis-year-start { text-align: left; }

.slider-row { margin-top: 20rpx; }
.year-slider { margin: 0 8rpx; }
.slider-readout {
  display: flex;
  align-items: baseline;
  justify-content: center;
  padding-top: 6rpx;
}
.ro-year { font-size: 34rpx; font-weight: 700; color: $color-ink; margin-right: 14rpx; }
.ro-age { font-size: 27rpx; color: $color-ink-light; margin-right: 14rpx; font-weight: 500; }
.ro-gz { font-size: 27rpx; color: $color-vermilion; font-weight: 600; }

.detail-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 18rpx; }
.detail-delta { font-size: 30rpx; font-weight: 700; }
.delta-up { color: #B8483C; }
.delta-down { color: #2E7D6E; }
.detail-grid { display: flex; flex-wrap: wrap; }
.dt-cell { width: 33.33%; padding: 10rpx 0; display: flex; align-items: baseline; }
.dt-label { font-size: 27rpx; color: $color-ink-light; margin-right: 10rpx; font-weight: 500; }
.dt-value { font-size: 31rpx; color: $color-ink; font-weight: 600; }

.rel-wrap { margin-top: 16rpx; display: flex; flex-wrap: wrap; }
.rel-chip {
  font-size: 25rpx;
  padding: 7rpx 18rpx;
  border-radius: 999rpx;
  margin: 8rpx 12rpx 0 0;
  background: $color-border-light;
  color: $color-ink-light;
  font-weight: 500;
}
.rel-chong { color: #B8483C; border: 1rpx solid rgba(184, 72, 60, 0.4); background: transparent; font-weight: 600; }
.rel-xing { color: #C2762A; border: 1rpx solid rgba(194, 118, 42, 0.35); background: transparent; font-weight: 600; }
.rel-hai { color: #8A7A3A; border: 1rpx solid rgba(138, 122, 58, 0.35); background: transparent; font-weight: 600; }
.rel-he { color: #2E7D6E; border: 1rpx solid rgba(46, 125, 110, 0.38); background: transparent; font-weight: 600; }
.rel-fu { color: $color-ink-light; border: 1rpx solid $color-border; background: transparent; }
.rel-empty { display: block; margin-top: 16rpx; font-size: 26rpx; color: $color-ink-light; }

.detail-actions { display: flex; justify-content: flex-end; margin-top: 18rpx; }
.act-pill {
  font-size: 26rpx;
  color: $color-primary;
  border: 1rpx solid $color-primary;
  border-radius: 999rpx;
  padding: 8rpx 24rpx;
  font-weight: 500;
}

.anno-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 16rpx;
}
.anno-scope { font-size: 26rpx; color: $color-ink-light; font-weight: 500; }
.anno-text { display: block; font-size: 30rpx; line-height: 1.85; color: $color-ink; font-weight: 400; letter-spacing: 0.5rpx; }
.anno-foot { display: block; margin-top: 16rpx; font-size: 24rpx; color: $color-ink-light; line-height: 1.6; }
.anno-state { padding: 8rpx 0; }
.anno-hint { display: block; font-size: 28rpx; color: $color-ink-light; line-height: 1.7; font-weight: 500; }
.anno-issue { display: block; margin-top: 10rpx; font-size: 25rpx; color: $color-ink-light; line-height: 1.6; }

/* ---- 反馈闭环 ---- */
.fb-wrap {
  margin-top: 20rpx;
  padding-top: 18rpx;
  border-top: 1rpx solid $color-border;
}
.fb-label { display: block; font-size: 26rpx; color: $color-ink-light; font-weight: 500; }
.fb-row { display: flex; margin-top: 14rpx; }
.fb-pill {
  font-size: 26rpx;
  color: $color-ink-light;
  border: 1rpx solid $color-border;
  border-radius: 999rpx;
  padding: 8rpx 26rpx;
  margin-right: 16rpx;
  font-weight: 500;
}
.fb-pill-on { color: $color-primary; border-color: $color-primary; font-weight: 600; }
.fb-msg { display: block; margin-top: 12rpx; font-size: 24rpx; color: $color-ink-light; line-height: 1.6; }

/* ---- 合盘共振线 ---- */
.reso-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 16rpx;
}
.reso-tag { font-size: 26rpx; color: $color-ink-light; font-weight: 500; }
.reso-hint { display: block; font-size: 26rpx; line-height: 1.7; color: $color-ink-light; }
.reso-form { margin-top: 18rpx; }
.reso-input {
  height: 68rpx;
  font-size: 25rpx;
  color: $color-ink;
  border: 1rpx solid $color-border;
  border-radius: 10rpx;
  padding: 0 18rpx;
  background: transparent;
}
.reso-ph { color: $color-ink-lightest; font-size: 24rpx; }
.reso-row { display: flex; align-items: center; margin-top: 16rpx; }
.reso-g {
  font-size: 23rpx;
  color: $color-ink-lighter;
  border: 1rpx solid $color-border;
  border-radius: 999rpx;
  padding: 6rpx 24rpx;
  margin-right: 14rpx;
}
.reso-g-on { color: $color-primary; border-color: $color-primary; }
.reso-go { margin-left: auto; }
.reso-err { display: block; margin-top: 12rpx; font-size: 21rpx; color: $color-ink-lighter; }

.reso-sum { margin-bottom: 12rpx; }
.reso-sum-item { display: block; font-size: 21rpx; line-height: 1.7; color: $color-ink-lighter; }

.reso-scroll { margin-top: 8rpx; white-space: nowrap; }
.reso-canvas { position: relative; }
.reso-plot { position: relative; width: 100%; }
/* 50 分中线：共振分以 50 为"平稳"，没有它就分不清柱子是在中线之上还是之下 */
.reso-mid {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 1rpx;
  background: $color-border;
}
.reso-col { position: absolute; bottom: 0; height: 100%; display: flex; align-items: flex-end; }
.reso-bar { width: 100%; border-radius: 2rpx 2rpx 0 0; }
.reso-sel { position: absolute; top: 0; bottom: 0; width: 2rpx; background: $color-primary; opacity: 0.55; margin-left: -1rpx; }
.reso-axis { position: relative; height: 30rpx; }
.reso-axis-year {
  position: absolute;
  font-size: 19rpx;
  color: $color-ink-lightest;
  text-align: center;
}
.reso-axis-first { text-align: left; }

.reso-detail { margin-top: 20rpx; padding-top: 16rpx; border-top: 1rpx solid $color-border; }
.reso-detail-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10rpx;
}
.reso-detail-year { font-size: 26rpx; color: $color-ink; }
.reso-detail-verdict { font-size: 24rpx; }
.rv-up { color: #B8483C; }
.rv-down { color: #2E7D6E; }
.rv-mid { color: $color-ink-lighter; }
.reso-terms { display: flex; flex-wrap: wrap; margin-top: 8rpx; }
.reso-term {
  font-size: 20rpx;
  color: $color-ink-lightest;
  border: 1rpx solid $color-border;
  border-radius: 6rpx;
  padding: 2rpx 10rpx;
  margin: 6rpx 10rpx 0 0;
}
.reso-note { display: block; margin-top: 12rpx; font-size: 20rpx; line-height: 1.6; color: $color-ink-lightest; }

/* ---- 事件标注 ---- */
.ev-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 16rpx;
}
.ev-count { font-size: 26rpx; color: $color-ink-light; font-weight: 500; }
.ev-hint { display: block; font-size: 25rpx; line-height: 1.7; color: $color-ink-light; margin-top: 8rpx; }
.ev-form { margin-top: 6rpx; }
.ev-row { display: flex; align-items: center; margin-top: 18rpx; }
.ev-label { width: 130rpx; flex-shrink: 0; font-size: 27rpx; color: $color-ink-light; font-weight: 500; }
/* 档位/领域各自成组换行：直接摆在行里会被 flex 压扁，中文会被拆成竖排 */
.ev-pills { flex: 1; display: flex; flex-wrap: wrap; }
.ev-input {
  flex: 1;
  height: 72rpx;
  font-size: 28rpx;
  color: $color-ink;
  border: 1rpx solid $color-border;
  border-radius: 10rpx;
  padding: 0 20rpx;
  background: transparent;
  font-weight: 500;
}
.ev-num { flex: none; width: 240rpx; }
.ev-tip { display: block; margin: 12rpx 0 0 130rpx; font-size: 23rpx; color: $color-ink-light; line-height: 1.6; }
.ev-pill {
  flex-shrink: 0;
  white-space: nowrap;
  font-size: 27rpx;
  color: $color-ink-light;
  border: 1rpx solid $color-border;
  border-radius: 999rpx;
  padding: 7rpx 22rpx;
  margin: 0 14rpx 10rpx 0;
  font-weight: 500;
}
.ev-pill-on { color: $color-primary; border-color: $color-primary; font-weight: 600; }
.ev-msg { display: block; margin-top: 14rpx; font-size: 25rpx; color: $color-ink-light; line-height: 1.6; }
.ev-list { margin-top: 20rpx; }
.ev-item {
  display: flex;
  align-items: baseline;
  padding: 14rpx 0;
  border-top: 1rpx solid $color-border-light;
}
.ev-item-main { font-size: 27rpx; color: $color-ink; flex-shrink: 0; font-weight: 500; }
.ev-item-note {
  flex: 1;
  margin: 0 18rpx;
  font-size: 25rpx;
  color: $color-ink-light;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.ev-del { font-size: 25rpx; color: $color-ink-light; padding: 0 10rpx; }

/* 关系事件嵌在共振卡里，用分隔线跟上面的曲线拉开层次而不是再套一层卡片 */
.pair-ev {
  margin-top: 28rpx;
  padding-top: 24rpx;
  border-top: 1rpx solid $color-border-light;
}
.pair-ev-head { display: flex; align-items: baseline; justify-content: space-between; }
.pair-ev-title { font-size: 28rpx; font-weight: 700; color: $color-ink; }
.pair-ev-count { font-size: 26rpx; color: $color-ink-light; font-weight: 500; }
.pair-ev-hint { display: block; margin-top: 10rpx; font-size: 25rpx; line-height: 1.7; color: $color-ink-light; }
.bt-line {
  display: block;
  margin-top: 16rpx;
  font-size: 25rpx;
  line-height: 1.7;
  color: $color-ink;
  font-weight: 400;
}
.bt-line-idle { color: $color-ink-light; }

.foot-note { padding: 10rpx 10rpx 28rpx; }
.fn-text { display: block; font-size: 25rpx; color: $color-ink-light; line-height: 1.9; }
</style>