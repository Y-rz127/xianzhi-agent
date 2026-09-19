<template>
  <view :class="['page-root', themeClass]">
    <!-- 自定义导航 -->
    <view class="navbar" :style="{ paddingTop: statusBarHeight + 'px' }">
      <view class="navbar-inner">
        <text class="nav-back" @tap="goBack">‹ 返回</text>
        <text class="nav-title display-font">命盘详情</text>
        <text class="nav-copy" @tap="copyChartText">{{ copied ? '已复制' : '复制' }}</text>
      </view>
    </view>

    <view v-if="loading" class="page-state">正在排盘…</view>
    <view v-else-if="!chart" class="page-state">缺少出生信息，无法排盘。请从先知对话、档案或命例库进入。</view>

    <template v-else>
      <!-- tab 栏 -->
      <scroll-view class="tab-bar" scroll-x :show-scrollbar="false">
        <view class="tab-row">
          <text
            v-for="tab in tabs"
            :key="tab.key"
            :class="['tab-btn', activeTab === tab.key && 'tab-active', tab.to && 'tab-link']"
            @tap="onTabTap(tab)"
          >{{ tab.label }}</text>
        </view>
      </scroll-view>

      <scroll-view class="page-body" :key="activeTab" scroll-y>
        <!-- 命盘：四柱 -->
        <view class="section section-flush" v-if="activeTab === 'paipan'">
          <view class="bazi-table bazi-table-4">
            <view class="bt-row bt-head">
              <text class="bt-cell bt-label"></text>
              <text v-for="c in mainColumns" :key="'h' + c.name" :class="['bt-cell bt-col-head', c.isCur && 'bt-cur-head']">{{ c.name }}</text>
            </view>
            <view class="bt-row">
              <text class="bt-cell bt-label">主星</text>
              <view v-for="c in mainColumns" :key="'m' + c.name" :class="['bt-cell']">
                <text v-if="c.name === '日柱'" class="bt-day-master">元{{ gender === '女' ? '女' : '男' }}</text>
                <text v-else-if="c.shishen && isShishen(c.shishen)" class="bt-shishen-tag" @tap="showShishenInfo(c.shishen)">{{ c.shishen }}</text>
                <text v-else class="bt-shishen">{{ c.shishen || '—' }}</text>
              </view>
            </view>
            <view class="bt-row">
              <text class="bt-cell bt-label">天干</text>
              <view v-for="c in mainColumns" :key="'g' + c.name" :class="['bt-cell']">
                <text class="bt-gan" :style="{ color: ganColor(c.gan) }">{{ c.gan || '—' }}</text>
              </view>
            </view>
            <view class="bt-row">
              <text class="bt-cell bt-label">地支</text>
              <view v-for="c in mainColumns" :key="'z' + c.name" :class="['bt-cell']">
                <text class="bt-zhi" :style="{ color: zhiColor(c.zhi) }">{{ c.zhi || '—' }}</text>
              </view>
            </view>
            <view class="bt-row">
              <text class="bt-cell bt-label">藏干</text>
              <view v-for="c in mainColumns" :key="'c' + c.name" :class="['bt-cell bt-multi']">
                <text v-for="(g, i) in c.hiddenStems" :key="i" class="bt-cang" :style="{ color: ganColor(g) }">{{ g }}</text>
              </view>
            </view>
            <view class="bt-row">
              <text class="bt-cell bt-label">副星</text>
              <view v-for="c in mainColumns" :key="'f' + c.name" :class="['bt-cell bt-multi']">
                <text v-for="(s, i) in c.shishenZhi" :key="i" :class="['bt-fu', isShishen(s) && 'bt-fu-click']" @tap="showShishenInfo(s)">{{ s }}</text>
              </view>
            </view>
            <view class="bt-row">
              <text class="bt-cell bt-label">星运</text>
              <view v-for="c in mainColumns" :key="'cs' + c.name" :class="['bt-cell']"><text class="bt-cs">{{ c.changsheng || '—' }}</text></view>
            </view>
            <view class="bt-row">
              <text class="bt-cell bt-label">自坐</text>
              <view v-for="c in mainColumns" :key="'zz' + c.name" :class="['bt-cell']"><text class="bt-cs">{{ c.zizuo || '—' }}</text></view>
            </view>
            <view class="bt-row">
              <text class="bt-cell bt-label">空亡</text>
              <view v-for="c in mainColumns" :key="'xk' + c.name" :class="['bt-cell']"><text class="bt-cs">{{ c.xunkong || '—' }}</text></view>
            </view>
            <view class="bt-row">
              <text class="bt-cell bt-label">纳音</text>
              <view v-for="c in mainColumns" :key="'ny' + c.name" :class="['bt-cell']"><text class="bt-nayin">{{ c.nayin || '—' }}</text></view>
            </view>
            <!-- 神煞直接融进命盘表最后一行 -->
            <view class="bt-row">
              <text class="bt-cell bt-label">神煞</text>
              <view v-for="c in mainColumns" :key="'ss' + c.name" :class="['bt-cell bt-multi']">
                <text v-if="!(shenshaByPillar[c.name] || []).length" class="ss-empty">—</text>
                <text v-for="(s, i) in (shenshaByPillar[c.name] || [])" :key="i" :class="['ss-tag', 'ss-' + s._cat]" @tap="showShenshaDesc(s)">{{ s.name }}</text>
              </view>
            </view>
          </view>
        </view>

        <!-- 基本信息（出生信息 + 五行 + 日主/调候） -->
        <view class="section" v-if="activeTab === 'paipan'">
          <view class="section-title-row">
            <text class="section-title flat">基本信息</text>
            <text class="gong-info">{{ birthTime }} · {{ gender }}命</text>
          </view>
          <view class="gong-summary display-font" v-if="chart.taiYuan || chart.mingGong || chart.shenGong">
            <text v-if="chart.taiYuan">胎元 {{ chart.taiYuan }}</text>
            <text v-if="chart.taiYuan && (chart.mingGong || chart.shenGong)"> · </text>
            <text v-if="chart.mingGong">命宫 {{ chart.mingGong }}</text>
            <text v-if="(chart.taiYuan || chart.mingGong) && chart.shenGong"> · </text>
            <text v-if="chart.shenGong">身宫 {{ chart.shenGong }}</text>
          </view>
          <view v-if="wuxing.length" class="wuxing-grid">
            <view v-for="w in wuxing" :key="w.name" class="wuxing-item">
              <view class="wuxing-bar-container">
                <view class="wuxing-bar" :style="{ height: (w.count / maxWuxing * 100) + '%', background: w.color }"></view>
              </view>
              <text class="wuxing-label" :style="{ color: w.color }">{{ w.name }}</text>
              <text class="wuxing-count">{{ w.count }}</text>
            </view>
          </view>
          <view v-if="chart.analysis?.strength" class="basic-row">
            <text class="basic-info basic-info-main">日主 {{ chart.analysis.day_master }}{{ chart.analysis.strength }}（置信度 {{ chart.analysis.confidence || '-' }}）</text>
          </view>
          <view v-if="chart.analysis?.adjustment" class="basic-row"><text class="basic-info">{{ chart.analysis.adjustment }}</text></view>
        </view>

        <!-- 起运信息 -->
        <view class="section" v-if="activeTab === 'paipan' && (startYunText || xipan?.qiyun)">
          <view class="qiyun-row">
            <view class="qiyun-left">
              <text class="qiyun-tag">起运</text>
              <text class="qiyun-after">{{ xipan?.qiyun?.after || startYunText?.after || '出生后起运' }}</text>
            </view>
            <view class="qiyun-meta">
              <text v-if="xipan?.qiyun" class="qiyun-sub">交运 {{ xipan.qiyun.startDate }} · {{ xipan.qiyun.jieqi }}后{{ xipan.qiyun.daysAfterJieqi }}天</text>
              <text v-else-if="startYunText" class="qiyun-sub">交运 {{ startYunText.date }} · {{ startYunText.dir }}</text>
            </view>
          </view>
          <!-- 月令旺衰 + 人元司令 -->
          <view v-if="xipan" class="xp-state-row">
            <view class="xp-state-block">
              <text class="xp-state-title">月令旺衰</text>
              <view class="xp-state-items">
                <text v-for="w in xipan.wuxingState" :key="w.name" class="xp-state-item" :class="'xs-' + xsStateKey(w.state)">{{ w.name }}{{ w.state }}</text>
              </view>
            </view>
            <view v-if="xipan.siling && xipan.siling.stem" class="xp-state-block">
              <text class="xp-state-title">人元司令</text>
              <view class="xp-state-items"><text class="xp-siling">{{ xipan.siling.stem }} 司令</text></view>
              <text class="xp-siling-detail">{{ xipan.siling.detail }}</text>
            </view>
          </view>
        </view>

        <!-- 排盘提示 -->
        <view class="section" v-if="activeTab === 'paipan' && warnings.length">
          <text class="section-title">排盘提示</text>
          <view class="warning-list">
            <text v-for="(w, i) in warnings" :key="i" class="warning-item">{{ w }}</text>
          </view>
        </view>

        <!-- 细盘：时间层级 -->
        <view class="section" v-if="activeTab === 'xipan'">
          <template v-if="xipan">
            <!-- 命盘大表：四柱 + 当前大运/流年，一屏放下 -->
            <view class="section inner section-flush">
              <view class="pd-table">
                <view class="pd-row pd-head">
                  <text class="pd-cell pd-label">日期</text>
                  <text
                    v-for="c in snapColumns"
                    :key="'h' + c.name"
                    :class="['pd-cell pd-col-head', (c.name === '大运' || c.name === '流年') && 'pd-cur-head']"
                  >{{ c.name }}</text>
                </view>
                <view class="pd-row">
                  <text class="pd-cell pd-label">主星</text>
                  <view v-for="c in snapColumns" :key="'m' + c.name" class="pd-cell">
                    <text v-if="c.name === '日柱'" class="pd-day-master">元{{ gender === '女' ? '女' : '男' }}</text>
                    <text v-else-if="isShishen(c.shishen)" class="pd-shishen pd-click" @tap="showShishenInfo(c.shishen)">{{ c.shishen }}</text>
                    <text v-else class="pd-shishen">{{ c.shishen || '—' }}</text>
                  </view>
                </view>
                <view class="pd-row">
                  <text class="pd-cell pd-label">天干</text>
                  <view v-for="c in snapColumns" :key="'g' + c.name" class="pd-cell">
                    <text class="pd-gan" :style="{ color: ganColor(c.gan) }">{{ c.gan || '—' }}</text>
                  </view>
                </view>
                <view class="pd-row">
                  <text class="pd-cell pd-label">地支</text>
                  <view v-for="c in snapColumns" :key="'z' + c.name" class="pd-cell">
                    <text class="pd-gan" :style="{ color: zhiColor(c.zhi) }">{{ c.zhi || '—' }}</text>
                  </view>
                </view>
                <view class="pd-row">
                  <text class="pd-cell pd-label">藏干</text>
                  <view v-for="c in snapColumns" :key="'c' + c.name" class="pd-cell pd-stack">
                    <view v-for="(g, i) in (c.hiddenStems || [])" :key="i" class="pd-cang-row">
                      <text class="pd-cang" :style="{ color: ganColor(g) }">{{ g }}</text>
                      <text class="pd-cang-ss" @tap="showShishenInfo((c.shishenZhi || [])[i])">{{ (c.shishenZhi || [])[i] || '' }}</text>
                    </view>
                    <text v-if="!(c.hiddenStems || []).length" class="ss-empty">—</text>
                  </view>
                </view>
                <view class="pd-row">
                  <text class="pd-cell pd-label">星运</text>
                  <text v-for="c in snapColumns" :key="'cs' + c.name" class="pd-cell pd-text">{{ c.changsheng || '—' }}</text>
                </view>
                <view class="pd-row">
                  <text class="pd-cell pd-label">自坐</text>
                  <text v-for="c in snapColumns" :key="'zz' + c.name" class="pd-cell pd-text">{{ c.zizuo || '—' }}</text>
                </view>
                <view class="pd-row">
                  <text class="pd-cell pd-label">空亡</text>
                  <text v-for="c in snapColumns" :key="'xk' + c.name" class="pd-cell pd-text">{{ c.xunkong || '—' }}</text>
                </view>
                <view class="pd-row">
                  <text class="pd-cell pd-label">纳音</text>
                  <text v-for="c in snapColumns" :key="'ny' + c.name" class="pd-cell pd-text">{{ c.nayin || '—' }}</text>
                </view>
                <view class="pd-row">
                  <text class="pd-cell pd-label">神煞</text>
                  <view v-for="c in snapColumns" :key="'ss' + c.name" class="pd-cell pd-stack">
                    <text v-if="!(snapShenshaMap[c.name] || []).length" class="ss-empty">—</text>
                    <text
                      v-for="(s, i) in (snapShenshaMap[c.name] || [])"
                      :key="i"
                      :class="['pd-ss-tag', 'ss-' + s._cat]"
                      @tap="showShenshaDesc(s)"
                    >{{ s.name }}</text>
                  </view>
                </view>
              </view>
            </view>

            <!-- 岁运横条：点大运看该运流年，点流年看该年流月 -->
            <view class="strip-hint-row">
              <text class="strip-ctx">{{ selectedDayunLabel || '童限' }} · {{ selectedYear }}年</text>
              <text class="strip-hint">点大运看流年 · 点流年看流月</text>
            </view>

            <!-- 大运横条（10 运并排 + 星运行） -->
            <view class="section inner">
              <view class="strip-container" :style="stripBox(ROWS_DAYUN)">
                <view class="strip-labels-fixed">
                  <view class="strip-labels-grid" :style="labelGrid(ROWS_DAYUN)">
                    <text class="strip-cell strip-label">大运</text>
                    <text class="strip-cell strip-label">星运</text>
                  </view>
                </view>
                <scroll-view scroll-x class="strip-scroll-content" :show-scrollbar="false">
                  <view class="strip-grid" :style="stripGrid(dayunCols.length, ROWS_DAYUN)">
                    <view
                      v-for="d in dayunCols"
                      :key="'dy' + d.index"
                      :class="['strip-cell', 'strip-click', d.isCur && 'strip-cur', d.isSel && 'strip-sel']"
                      @tap="selectDayun(d.index)"
                    >
                      <text class="sc-year">{{ d.startYear }}</text>
                      <text class="sc-age">{{ d.ageText }}</text>
                      <view class="sc-gz">
                        <text :class="['sc-gan', d.isTongxian && 'sc-tongxian']" :style="d.isTongxian ? {} : { color: ganColor(d.gan) }">{{ d.gan }}</text>
                        <text class="sc-ss">{{ d.ganSs }}</text>
                      </view>
                      <view class="sc-gz">
                        <text :class="['sc-gan', d.isTongxian && 'sc-tongxian']" :style="d.isTongxian ? {} : { color: zhiColor(d.zhi) }">{{ d.zhi }}</text>
                        <text class="sc-ss">{{ d.zhiSs }}</text>
                      </view>
                    </view>
                    <text v-for="d in dayunCols" :key="'dcs' + d.index" class="strip-cell sc-cs">{{ d.changsheng || '—' }}</text>
                  </view>
                </scroll-view>
              </view>
            </view>

            <!-- 流年横条（所选大运 10 年 + 小运行 + 星运行） -->
            <view class="section inner" v-if="liunianCols.length">
              <view class="strip-container" :style="stripBox(ROWS_LIUNIAN)">
                <view class="strip-labels-fixed">
                  <view class="strip-labels-grid" :style="labelGrid(ROWS_LIUNIAN)">
                    <text class="strip-cell strip-label">流年</text>
                    <text class="strip-cell strip-label">小运</text>
                    <text class="strip-cell strip-label">星运</text>
                  </view>
                </view>
                <scroll-view scroll-x class="strip-scroll-content" :show-scrollbar="false">
                  <view class="strip-grid" :style="stripGrid(liunianCols.length, ROWS_LIUNIAN)">
                    <view
                      v-for="l in liunianCols"
                      :key="'ln' + l.year"
                      :class="['strip-cell', 'strip-click', l.isCur && 'strip-cur', l.isSel && 'strip-sel']"
                      @tap="selectYear(l.year)"
                    >
                      <text class="sc-year">{{ l.year }}</text>
                      <view class="sc-gz">
                        <text class="sc-gan" :style="{ color: ganColor(l.gan) }">{{ l.gan }}</text>
                        <text class="sc-ss">{{ l.ganSs }}</text>
                      </view>
                      <view class="sc-gz">
                        <text class="sc-gan" :style="{ color: zhiColor(l.zhi) }">{{ l.zhi }}</text>
                        <text class="sc-ss">{{ l.zhiSs }}</text>
                      </view>
                    </view>
                    <text v-for="l in liunianCols" :key="'lxy' + l.year" class="strip-cell sc-xy">{{ l.xiaoyun || '—' }}</text>
                    <text v-for="l in liunianCols" :key="'lcs' + l.year" class="strip-cell sc-cs">{{ l.changsheng || '—' }}</text>
                  </view>
                </scroll-view>
              </view>
            </view>

            <!-- 流月横条（选中流年 12 节气月 + 星运行，可横滑） -->
            <view class="section inner" v-if="liuyueCols.length">
              <view class="strip-container" :style="stripBox(ROWS_LIUYUE)">
                <view class="strip-labels-fixed">
                  <view class="strip-labels-grid" :style="labelGrid(ROWS_LIUYUE)">
                    <text class="strip-cell strip-label">流月</text>
                    <text class="strip-cell strip-label">星运</text>
                  </view>
                </view>
                <scroll-view scroll-x class="strip-scroll-content" :show-scrollbar="false">
                  <view class="strip-grid" :style="stripGrid(liuyueCols.length, ROWS_LIUYUE)">
                    <view
                      v-for="m in liuyueCols"
                      :key="'ly' + m.key"
                      :class="['strip-cell', 'strip-click', m.isCur && 'strip-cur', m.isSel && 'strip-sel']"
                      @tap="selectLiuyue(m.raw)"
                    >
                      <text class="sc-jie">{{ m.jieqi }}</text>
                      <text class="sc-age">{{ m.date }}</text>
                      <view class="sc-gz">
                        <text class="sc-gan" :style="{ color: ganColor(m.gan) }">{{ m.gan }}</text>
                        <text class="sc-ss">{{ m.ganSs }}</text>
                      </view>
                      <view class="sc-gz">
                        <text class="sc-gan" :style="{ color: zhiColor(m.zhi) }">{{ m.zhi }}</text>
                        <text class="sc-ss">{{ m.zhiSs }}</text>
                      </view>
                    </view>
                    <text v-for="m in liuyueCols" :key="'lys' + m.key" class="strip-cell sc-cs">{{ m.changsheng || '—' }}</text>
                  </view>
                </scroll-view>
              </view>
            </view>

            <!-- 起运 / 当前岁数 / 司令 -->
            <view class="xp-topbar">
              <view class="xp-top-qiyun">
                <text class="xp-top-tag">起运</text>
                <text class="xp-top-after">{{ xipan.qiyun.after }}</text>
                <text class="xp-top-sub">交运 {{ xipan.qiyun.startDate }} · {{ xipan.qiyun.jieqi }}后{{ xipan.qiyun.daysAfterJieqi }}天</text>
              </view>
              <view class="xp-top-meta">
                <text class="xp-top-age">{{ gender }} · {{ xipan.current.year }}年 {{ xipan.current.age }}虚岁</text>
                <text v-if="xipan.siling?.stem" class="xp-top-siling">司令：{{ xipan.siling.stem }}</text>
              </view>
            </view>

            <!-- 岁运分析（大运 · 流年 · 流月 叠加原局） -->
            <view class="section inner" v-if="suiyunRows.length">
              <view class="section-title-row">
                <text class="section-title flat">岁运分析</text>
                <text class="gong-info">{{ relations?.suiyun.label }}{{ relationsLoading ? ' · 计算中…' : '' }}</text>
              </view>
              <view v-for="row in suiyunRows" :key="'sy' + row.label" class="an-row">
                <text class="an-label">{{ row.label }}</text>
                <view class="an-tags">
                  <text v-if="!row.items.length" class="ss-empty">—</text>
                  <text v-for="(it, i) in row.items" :key="i" class="an-tag">{{ it }}</text>
                </view>
              </view>
            </view>

            <!-- 原局分析（四柱内部关系） -->
            <view class="section inner" v-if="yuanjuRows.length">
              <view class="section-title-row">
                <text class="section-title flat">原局分析</text>
                <text class="gong-info">{{ relations?.yuanju.label }}</text>
              </view>
              <view v-for="row in yuanjuRows" :key="'yj' + row.label" class="an-row">
                <text class="an-label">{{ row.label }}</text>
                <view class="an-tags">
                  <text v-if="!row.items.length" class="ss-empty">—</text>
                  <text v-for="(it, i) in row.items" :key="i" class="an-tag">{{ it }}</text>
                </view>
              </view>
            </view>

            <!-- 四柱神煞（横向：每柱一行，柱名在左、神煞 tag 在右横排） -->
            <view class="section inner" v-if="pillars.length">
              <text class="section-title">四柱神煞</text>
              <view v-for="p in pillars" :key="p.name" class="ss-row">
                <text class="ss-gz" :style="{ color: '#8a6d3b' }">{{ p.ganzhi }}</text>
                <view class="ss-list">
                  <text v-if="!(shenshaByPillar[p.name] || []).length" class="ss-empty">—</text>
                  <text v-for="(s, i) in (shenshaByPillar[p.name] || [])" :key="i" :class="['ss-tag', 'ss-' + s._cat]" @tap="showShenshaDesc(s)">{{ s.name }}</text>
                </view>
              </view>
            </view>
            <view class="section inner" v-if="dayunShenshaList.length">
              <view class="section-title-row">
                <text class="section-title flat">大运神煞</text>
                <text class="ss-toggle" @tap="showAllDayunShensha = !showAllDayunShensha">{{ showAllDayunShensha ? '只看所选大运 ▲' : '全部大运 ▼' }}</text>
              </view>
              <view v-for="d in dayunShenshaList" :key="d.ganzhi + d.range" :class="['ss-row', d.isSel && 'ss-cur-row']">
                <view :class="['ss-gz-col', (d.isSel || d.isCurrent) && 'ss-gz-cur']">
                  <text class="ss-gz-main">{{ d.ganzhi }}</text>
                  <text class="ss-gz-sub">{{ d.rangeShort }}</text>
                </view>
                <view class="ss-list">
                  <text v-if="!d.list.length" class="ss-empty">—</text>
                  <text v-for="(s, i) in d.list" :key="i" :class="['ss-tag', 'ss-' + classifyShensha(s)]" @tap="showShenshaDesc(s)">{{ s.name }}</text>
                </view>
              </view>
            </view>
            <view class="section inner">
              <view class="section-title-row">
                <text class="section-title flat">流年神煞</text>
                <text class="ss-toggle" @tap="showAllYearShensha = !showAllYearShensha">{{ showAllYearShensha ? '只看所选流年 ▲' : '该运全部流年 ▼' }}</text>
              </view>
              <view v-for="y in yearShenshaList" :key="y.year" :class="['ss-row', y.isSel && 'ss-cur-row']">
                <text :class="['ss-gz', (y.isSel || y.isCurrent) && 'ss-gz-cur']">{{ y.year }} {{ y.gz }}</text>
                <view class="ss-list">
                  <text v-for="(s, i) in y.list" :key="i" :class="['ss-tag', 'ss-' + classifyShensha(s)]" @tap="showShenshaDesc(s)">{{ s.name }}</text>
                </view>
              </view>
            </view>

            <!-- 流月神煞：跟随选中的流年，点击流月格可聚焦 -->
            <view class="section inner" v-if="monthShenshaRows.length">
              <view class="section-title-row">
                <text class="section-title flat">流月神煞</text>
                <text class="ss-toggle" @tap="showAllMonthShensha = !showAllMonthShensha">{{ showAllMonthShensha ? '只看所选流月 ▲' : '该年全部流月 ▼' }}</text>
              </view>
              <view
                v-for="mo in monthShenshaRows"
                :key="mo.key"
                :class="['ss-row', mo.isSelected && 'ss-cur-row']"
              >
                <text :class="['ss-gz ss-gz-wide', mo.isCurrent && 'ss-gz-cur']">{{ mo.jieqi }} {{ mo.gz }}</text>
                <view class="ss-list">
                  <text v-if="!mo.list.length" class="ss-empty">—</text>
                  <text v-for="(s, i) in mo.list" :key="i" :class="['ss-tag', 'ss-' + classifyShensha(s)]" @tap="showShenshaDesc(s)">{{ s.name }}</text>
                </view>
              </view>
            </view>

            <view v-if="xipan.note" class="xipan-note"><text>{{ xipan.note }}</text></view>
          </template>
          <view v-else class="page-state small">暂无细盘数据</view>
        </view>

        <!-- AI 报告 -->
        <view class="section" v-if="activeTab === 'notes'">
          <text class="section-title">AI 命理报告</text>
          <view v-if="reportLoading" class="report-loading"><text>正在由先知生成报告…</text></view>
          <view v-else-if="reportContent" class="report-content">
            <MarkdownRender :content="reportContent" />
          </view>
          <view v-else class="report-placeholder"><text>点击下方按钮生成 AI 分节命理报告</text></view>
        </view>

        <view class="bottom-spacer"></view>
      </scroll-view>

      <!-- 底部操作栏 -->
      <view class="page-footer">
        <text v-if="!reportContent" class="fbtn" @tap="handleDownloadPdf">下载 PDF</text>
        <text :class="['fbtn', 'fbtn-primary', reportLoading && 'disabled']" @tap="generateReport">{{ reportLoading ? '生成中…' : (reportContent ? '重新生成报告' : '生成完整报告') }}</text>
        <text v-if="reportContent" class="fbtn" @tap="downloadFullPdf">导出完整 PDF</text>
      </view>
    </template>

    <!-- 大运/流年详情浮层 -->
    <view v-if="selectedDetail" class="detail-mask" @tap="closeDetail">
      <view class="detail-card" @tap.stop>
        <view class="detail-header">
          <text class="detail-title">{{ selectedDetail.ganzhi }}</text>
          <text class="detail-close" @tap="closeDetail">✕</text>
        </view>
        <text class="detail-sub">{{ detailSubtitle }}</text>
        <view class="detail-grid">
          <view class="detail-row"><text class="detail-label">主星</text><text class="detail-value">{{ selectedDetail.shishenGan || '—' }}</text></view>
          <view class="detail-row"><text class="detail-label">天干</text><text class="detail-value">{{ selectedDetail.gan || '—' }}</text></view>
          <view class="detail-row"><text class="detail-label">地支</text><text class="detail-value">{{ selectedDetail.zhi || '—' }}</text></view>
          <view class="detail-row"><text class="detail-label">藏干</text><text class="detail-value">{{ (selectedDetail.hiddenStems || []).join('、') || '—' }}</text></view>
          <view class="detail-row"><text class="detail-label">副星</text><text class="detail-value">{{ (selectedDetail.shishenZhi || []).join('、') || '—' }}</text></view>
          <view class="detail-row"><text class="detail-label">星运</text><text class="detail-value">{{ selectedDetail.changsheng || '—' }}</text></view>
        </view>
        <view v-if="selectedDetail.shensha && selectedDetail.shensha.length" class="detail-shensha-block">
          <text class="detail-shensha-title">神煞 <text class="detail-shensha-hint">点击查看详情</text></text>
          <view class="detail-shensha-tags">
            <view
              v-for="(s, i) in selectedDetail.shensha"
              :key="i"
              :class="['detail-shensha-tag', activeShenshaName === s.name && 'active']"
              @tap="toggleShenshaDesc(s.name, s.description)"
            ><text>{{ s.name }}</text></view>
          </view>
          <view v-if="activeShenshaName" class="detail-shensha-desc">
            <text class="detail-shensha-desc-name">{{ activeShenshaName }}</text>
            <text class="detail-shensha-desc-text">{{ activeShenshaDesc }}</text>
          </view>
        </view>
        <view class="detail-actions">
          <text class="detail-action-btn" @tap="closeDetail">关闭</text>
        </view>
      </view>
    </view>

    <!-- 十神特性浮层 -->
    <view v-if="shishenModal" class="shishen-mask" @tap="closeShishenModal">
      <view class="shishen-card" @tap.stop>
        <view class="shishen-header">
          <text class="shishen-title display-font">{{ shishenModal.name }}</text>
          <text class="shishen-close" @tap="closeShishenModal">✕</text>
        </view>
        <view class="shishen-body">
          <view class="shishen-section">
            <text class="shishen-label">【正面特性】</text>
            <text class="shishen-text">{{ shishenModal.positive }}</text>
          </view>
          <view class="shishen-section">
            <text class="shishen-label">【反面特性】</text>
            <text class="shishen-text">{{ shishenModal.negative }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { useTheme } from '@/composables/useTheme'
import { getChart, getRelations, generateFullReport, downloadReport, downloadFullReportPdf, isSameDayun, collapseBySelection, type ChartData, type Pillar, type WuxingItem, type DayunItem, type ShenshaItem, type LiuNianItem, type XiPanData, type XiPanLiuYue, type XiPanRelationGroup, type XiPanRelations } from '@/api'
import MarkdownRender from '@/components/MarkdownRender/MarkdownRender.vue'

const { themeClass } = useTheme()

type TabKey = 'paipan' | 'xipan' | 'notes'
// 「命理 K 线」占一个 tab 位、点了跳独立页（to 标记为外链 tab，永不成为 activeTab）：
// 它和命理报告同属「看结论」，排在报告左边；排盘/细盘属「看数据」，故在其右。
const tabs: { key: string; label: string; to?: boolean }[] = [
  { key: 'paipan', label: '基本排盘' },
  { key: 'xipan', label: '专业细盘' },
  { key: 'kline', label: '命理K线', to: true },
  { key: 'notes', label: '命理报告' },
]
const activeTab = ref<TabKey>('paipan')

function onTabTap(tab: { key: string; to?: boolean }) {
  if (tab.to) {
    goKline()
    return
  }
  activeTab.value = tab.key as TabKey
}

// 切 tab 回到顶部：scroll-view 由 :key 重建确定性归零；
// 再兜一层页面级滚动（全局 page 是 min-height:100vh，页面本身也可能被滚走）
watch(activeTab, () => {
  try { uni.pageScrollTo({ scrollTop: 0, duration: 0 }) } catch {}
})

const statusBarHeight = ref(20)
try {
  statusBarHeight.value = uni.getWindowInfo().statusBarHeight || 20
} catch {}

const chart = ref<ChartData | null>(null)
const loading = ref(true)
const birthTime = ref('')
const gender = ref('')

const ganWx: Record<string, string> = {
  '甲': '#4ade80', '乙': '#4ade80',
  '丙': '#f87171', '丁': '#f87171',
  '戊': '#d4a574', '己': '#d4a574',
  '庚': '#fbbf24', '辛': '#fbbf24',
  '壬': '#60a5fa', '癸': '#60a5fa',
}
const zhiWx: Record<string, string> = {
  '寅': '#4ade80', '卯': '#4ade80',
  '巳': '#f87171', '午': '#f87171',
  '辰': '#d4a574', '戌': '#d4a574', '丑': '#d4a574', '未': '#d4a574',
  '申': '#fbbf24', '酉': '#fbbf24',
  '亥': '#60a5fa', '子': '#60a5fa',
}
const ganColor = (c: string) => ganWx[c] || '#e5e7eb'
const zhiColor = (c: string) => zhiWx[c] || '#e5e7eb'

const pillars = computed<Pillar[]>(() => chart.value?.pillars || [])
const wuxing = computed<WuxingItem[]>(() => chart.value?.wuxing || [])
const dayun = computed<DayunItem[]>(() => chart.value?.dayun || [])
const warnings = computed<string[]>(() => chart.value?.warnings || [])
const xipan = computed<XiPanData | null>(() => chart.value?.xipan || null)
const maxWuxing = computed(() => Math.max(...wuxing.value.map((w) => w.count), 1))

// 专业细盘快照列顺序：四柱在前，大运/流年放到右侧
const SNAP_ORDER = ['年柱', '月柱', '日柱', '时柱', '大运', '流年']

// 点选后命盘大表实际展示的大运/流年干支（童限段无干支，以该年小运代位）
const snapDayunGz = computed(() => {
  const xp = xipan.value
  if (!xp) return ''
  const dy = xp.dayun.find((d) => d.index === selectedDayunIndex.value)
  if (!dy) return ''
  return dy.ganzhi.length === 2 ? dy.ganzhi : xp.liunian.find((l) => l.year === selectedYear.value)?.xiaoyun || ''
})
const snapLiunianGz = computed(() =>
  xipan.value?.liunian.find((l) => l.year === selectedYear.value)?.ganzhi || '')

// 命盘大表的大运/流年两列跟随用户点选：字段查 ganzhiMeta（60 干支纯函数表，与后端 snapshot 逐字段一致）
const snapColumns = computed(() => {
  const xp = xipan.value
  if (!xp) return []
  const cols = [...(xp.snapshot?.columns || []).filter((c) => SNAP_ORDER.indexOf(c.name) < 4)]
  const meta = xp.ganzhiMeta || {}
  const col = (name: string, gz: string) => {
    const m = meta[gz]
    return {
      name,
      ganzhi: gz || '—',
      shishen: m?.shishen || '',
      gan: m?.gan || '',
      zhi: m?.zhi || '',
      hiddenStems: m?.hiddenStems || [],
      shishenZhi: m?.shishenZhi || [],
      changsheng: m?.changsheng || '',
      zizuo: m?.zizuo || '',
      xunkong: m?.xunkong || '',
      nayin: m?.nayin || '',
    }
  }
  cols.push(col('大运', snapDayunGz.value))
  cols.push(col('流年', snapLiunianGz.value))
  return cols
})

const currentYear = new Date().getFullYear()
const currentDayun = computed(() =>
  dayun.value.find((d) => d.startYear <= currentYear && (d.endYear || d.startYear + 9) >= currentYear) || dayun.value[0]
)

interface MainCol {
  name: string
  ganzhi: string
  gan: string
  zhi: string
  shishen: string
  hiddenStems: string[]
  shishenZhi: string[]
  changsheng: string
  zizuo: string
  xunkong: string
  nayin: string
  isCur: boolean
}

// 命盘主表四列：年柱、月柱、日柱、时柱（基本排盘只展示四柱，大运/流年在专业细盘）
const mainColumns = computed<MainCol[]>(() => {
  return pillars.value.map((p) => ({
    name: p.name, ganzhi: p.ganzhi, gan: p.ganzhi[0] || '', zhi: p.ganzhi[1] || '',
    shishen: p.shishenGan || '',
    hiddenStems: p.hiddenStems || [], shishenZhi: p.shishenZhi || [],
    changsheng: p.changsheng || '', zizuo: p.zizuo || '', xunkong: p.xunkong || '', nayin: p.nayin || '',
    isCur: false,
  }))
})

// 神煞按柱分组（四柱），用于基本排盘的四列竖排展示
// 大运/流年神煞在细盘 tab 内另有 dayunShensha / yearShenshaList 处理

// 流年表展示选中大运覆盖的全部流年（10 个）
const liunianRows = computed(() => {
  const xp = xipan.value
  if (!xp) return []
  return xp.liunian.filter((l) => l.dayunIndex === selectedDayunIndex.value)
})

// === 细盘选中联动 ===
const selectedDayunIndex = ref(-1)
const selectedYear = ref(0)
const selectedLiuyueGz = ref('')

// === 岁运/原局分析（跟随点选） ===
// 初次进入用 /chart 里算好的那一组（对应"今天"），之后每次点大运/流年/流月回调 /relations 现算
const relations = ref<XiPanRelations | null>(null)
const relationsLoading = ref(false)
// 已对齐的"大运|流年|流月"组合：同组合不重复请求（也用于跳过初始化那次）
const relationsKey = ref('')
// 盘面参数（onLoad 里从路由参数取，供 /relations 复用）
const chartSect = ref(2)
const chartYunSect = ref(1)
const chartLongitude = ref<number | undefined>(undefined)
let relationsTimer: ReturnType<typeof setTimeout> | null = null

function currentRelationsKey(): string {
  return [snapDayunGz.value, snapLiunianGz.value, selectedLiuyueGz.value].join('|')
}

/** 点选变化 → 拉取该组合的六栏关系（150ms 防抖；过期响应丢弃，避免快速点选时串位） */
function refreshRelations() {
  const xp = xipan.value
  if (!xp || !birthTime.value || !gender.value) return
  const key = currentRelationsKey()
  if (!key.replace(/\|/g, '') || key === relationsKey.value) return
  if (relationsTimer) clearTimeout(relationsTimer)
  relationsTimer = setTimeout(async () => {
    relationsLoading.value = true
    try {
      const data = await getRelations(birthTime.value, gender.value, {
        sect: chartSect.value,
        yunSect: chartYunSect.value,
        longitude: chartLongitude.value,
        dayun: snapDayunGz.value,
        liunian: snapLiunianGz.value,
        liuyue: selectedLiuyueGz.value,
      })
      if (currentRelationsKey() !== key) return // 期间又点了别的，丢弃这次结果
      relations.value = data
      relationsKey.value = key
    } catch {
      /* 拉取失败保留旧结果，不打断浏览 */
    } finally {
      relationsLoading.value = false
    }
  }, 150)
}

// 点选大运/流年/流月 → 岁运分析跟随刷新
watch([selectedDayunIndex, selectedYear, selectedLiuyueGz, () => xipan.value], () => refreshRelations())

const liuyueOfYear = computed(() => {
  const xp = xipan.value
  return xp ? xp.liuyue.filter((m) => m.year === selectedYear.value) : []
})
const selectedDayunLabel = computed(() => {
  const xp = xipan.value
  if (!xp) return ''
  const d = xp.dayun.find((x) => x.index === selectedDayunIndex.value)
  return d ? `${d.index === 0 ? '童限' : d.ganzhi + ' 大运'} · ${d.startYear}-${d.endYear}` : ''
})

function initXipanSelection() {
  const xp = xipan.value
  if (xp) {
    selectedDayunIndex.value = xp.current.dayunIndex
    selectedYear.value = xp.current.year
    selectedLiuyueGz.value = xp.current.liuyue || ''
  }
}

function selectDayun(index: number) {
  selectedDayunIndex.value = index
  const first = xipan.value?.liunian.find((l) => l.dayunIndex === index)
  if (first) selectYear(first.year)
}
function selectYear(year: number) {
  selectedYear.value = year
  // 换流年默认落在该年第一个流月（立春），与「点大运落到该运首年」同规则；
  // 之后只有用户点别的流月才切换
  const first = xipan.value?.liuyue.find((m) => m.year === year)
  selectedLiuyueGz.value = first?.ganzhi || ''
}
function selectLiuyue(m: XiPanLiuYue) {
  selectedLiuyueGz.value = m.ganzhi
}
function isCurrentLiuyue(m: XiPanLiuYue): boolean {
  const xp = xipan.value
  return !!xp && selectedYear.value === xp.current.year && m.ganzhi === xp.current.liuyue
} 

// === 岁运横条（图2 样式）：大运 / 流年 / 流月 ===
// 十神单字缩写：横条列宽有限，与问真/元亨利贞同一套写法
const SS_SHORT: Record<string, string> = {
  比肩: '比', 劫财: '劫', 食神: '食', 伤官: '伤',
  偏财: '才', 正财: '财', 偏印: '枭', 正印: '印',
  七杀: '杀', 正官: '官',
}
const ssShort = (name?: string) => (name ? SS_SHORT[name] || name.slice(-1) : '')

/** 横条栅格：N 个 88rpx 等宽列（标签列已独立在滚动区之外），整条超出屏宽可横滑 */
function stripGrid(n: number, rows: string, col = 88) {
  return {
    gridTemplateColumns: `repeat(${n}, ${col}rpx)`,
    gridTemplateRows: rows,
    width: `${n * col}rpx`,
  }
}

/** 固定标签列的行高，必须与 stripGrid 的行模板一致，否则标签与内容错位 */
function labelGrid(rows: string) {
  return { gridTemplateRows: rows }
}

/** 横条容器精确高度 = 行高之和 + 1rpx 行缝 + 上下 1rpx 边框。
 *  mp-weixin 下 scroll-view 不给高度会把 flex 容器撑高，多出的部分露出容器灰底，
 *  看起来像表格下面多了一条空白行。 */
function stripBox(rows: string) {
  const heights = rows.split(' ').map((v) => parseInt(v, 10) || 0)
  const total = heights.reduce((a, b) => a + b, 0) + Math.max(0, heights.length - 1) + 2
  return { height: `${total}rpx` }
}

// 主格（年/岁/干支十神）+ 星运；流年多一行小运
const ROWS_DAYUN = '184rpx 56rpx'
const ROWS_LIUNIAN = '156rpx 56rpx 56rpx'
const ROWS_LIUYUE = '184rpx 56rpx'

const dayunCols = computed(() => {
  const xp = xipan.value
  return (xp?.dayun || []).map((d) => ({
    index: d.index,
    startYear: d.startYear,
    ageText: d.index === 0 ? `${d.startAge}~${d.endAge}岁` : `${d.startAge}岁`,
    gan: d.ganzhi[0] || '',
    zhi: d.ganzhi[1] || '',
    // 起运前的童限段没有干支，两字竖排显示、不走五行配色
    isTongxian: d.index === 0 || !/^[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]$/.test(d.ganzhi),
    ganSs: ssShort(d.shishen),
    zhiSs: ssShort((d.shishenZhi || [])[0]),
    changsheng: d.changsheng,
    isCur: d.index === (xp?.current?.dayunIndex ?? -1),
    isSel: d.index === selectedDayunIndex.value,
  }))
})

const liunianCols = computed(() => liunianRows.value.map((l) => ({
  year: l.year,
  gan: l.ganzhi[0] || '',
  zhi: l.ganzhi[1] || '',
  ganSs: ssShort(l.shishen),
  zhiSs: ssShort((l.shishenZhi || [])[0]),
  xiaoyun: l.xiaoyun,
  changsheng: l.changsheng,
  isCur: String(l.year) === String(xipan.value?.current?.year),
  isSel: l.year === selectedYear.value,
})))

const liuyueCols = computed(() => liuyueOfYear.value.map((m) => {
  // 地支十神/星运是月支的纯函数，后端按 12 条 monthMeta 去重下发
  const meta = xipan.value?.monthMeta?.[m.zhi]
  return {
    key: `${m.year}-${m.zhi}`,
    jieqi: m.jieqi,
    date: m.date,
    gan: m.ganzhi[0] || '',
    zhi: m.ganzhi[1] || '',
    ganSs: ssShort(m.shishen),
    zhiSs: ssShort((meta?.shishenZhi || [])[0]),
    changsheng: meta?.changsheng || '',
    isCur: isCurrentLiuyue(m),
    isSel: selectedLiuyueGz.value === m.ganzhi,
    raw: m,
  }
}))

// === 基本排盘：起运 + 大运/流年表 ===
const startYunText = computed(() => {
  const xp = xipan.value
  if (xp?.qiyun) {
    return { after: xp.qiyun.after, dir: xp.qiyun.direction, date: xp.qiyun.startDate }
  }
  const sy = chart.value?.startYun
  if (sy?.startDate) return { after: '', dir: sy.direction || '', date: sy.startDate }
  return null
})

// === 岁运分析 / 原局分析（后端 relations 引擎，六栏口径对齐专业排盘软件） ===
// 数据不再固定为"今天"那一组：跟随用户点选的大运/流年/流月回调后端现算（见 refreshRelations）
function relRows(g?: XiPanRelationGroup) {
  if (!g) return []
  return [
    { label: '天干', items: g.gan || [] },
    { label: '地支', items: g.zhi || [] },
    { label: '整柱', items: g.zhu || [] },
  ]
}
const suiyunRows = computed(() => relRows(relations.value?.suiyun))
const yuanjuRows = computed(() => relRows(relations.value?.yuanju))

// === 神煞列表（截图式：四柱/大运/流年） ===
const dayunShenshaRaw = computed(() => {
  const cur = currentDayun.value
  const sel = xipan.value?.dayun.find((d) => d.index === selectedDayunIndex.value)
  return (chart.value?.dayun || []).map((d) => ({
    ganzhi: d.ganzhi,
    range: `${d.startYear}-${d.endYear || d.startYear + 9}（${d.startAge}-${d.endAge || d.startAge + 9}岁）`,
    rangeShort: `${d.startYear}-${d.endYear || d.startYear + 9}`,
    isCurrent: isSameDayun(d, cur),
    isSel: isSameDayun(d, sel),
    list: d.shensha || [],
  }))
})
// 大运神煞折叠控制，默认只显示当前选中的那一步大运
const showAllDayunShensha = ref(false)
const dayunShenshaList = computed(() => {
  const rows = dayunShenshaRaw.value
  return collapseBySelection(rows, rows.filter((d) => d.isSel), showAllDayunShensha.value, selectedDayunIndex.value >= 0)
})
// 流年神煞：查 xipan.liunianShensha[干支]（60 条覆盖全部流年）+ shenshaDict[名] 取说明
// 旧实现按 year 合并顶层 chart.liunian，而那里只有当前大运十年有神煞，切别的运就空白
const showAllYearShensha = ref(false)
const yearShenshaList = computed(() => {
  const xp = xipan.value
  if (!xp) return []
  const index = xp.liunianShensha || {}
  const dict = xp.shenshaDict || {}
  const rows = xp.liunian
    .filter((l) => l.dayunIndex === selectedDayunIndex.value)
    .map((l) => ({
      year: l.year,
      gz: l.ganzhi,
      isCurrent: String(l.year) === String(xp.current.year),
      isSel: l.year === selectedYear.value,
      list: (index[l.ganzhi] || []).map((name) => ({ name, description: dict[name] || '' })),
    }))
    .sort((a, b) => Number(a.year) - Number(b.year))
  return collapseBySelection(rows, rows.filter((y) => y.isSel), showAllYearShensha.value, selectedYear.value > 0)
})

// 流月神煞：展示选中流年的 12 个节气月，点击流月格可聚焦对应行
const showAllMonthShensha = ref(false)
const monthShenshaRows = computed(() => {
  const xp = xipan.value
  if (!xp) return []
  const rows = xp.liuyue
    .filter((m) => m.year === selectedYear.value)
    .map((m) => ({
      key: `${m.year}-${m.zhi}`,
      jieqi: m.jieqi,
      gz: m.ganzhi,
      isCurrent: isCurrentLiuyue(m),
      isSelected: selectedLiuyueGz.value === m.ganzhi,
      // 流月神煞按干支索引去重下发：名查 liuyueShensha[ganzhi]，说明查 shenshaDict[name]
      list: (xp.liuyueShensha?.[m.ganzhi] || []).map((name) => ({
        name,
        description: (xp.shenshaDict || {})[name] || '',
      })),
    }))
  return collapseBySelection(rows, rows.filter((m) => m.isSelected), showAllMonthShensha.value, !!selectedLiuyueGz.value)
})

// 五行旺相休囚死的取色 class：用 ASCII 数字避免 WXSS 对中文 class 做 `\XXXX` 转义导致编译失败
const XS_STATE_KEY: Record<string, number> = { 旺: 0, 相: 1, 休: 2, 囚: 3, 死: 4 }
function xsStateKey(state: string): number {
  return XS_STATE_KEY[state] ?? 0
}

// === 神煞 ===
function classifyShensha(item: ShenshaItem): string {
  const text = `${item.name} ${item.description}`
  if (/桃花|红鸾|天喜|沐浴|咸池|红艳|情缘|感情|姻缘|婚/.test(text)) return 'love'
  if (/羊刃|劫煞|亡神|灾煞|元辰|空亡|十恶大败|阴差阳错|天罗地网|飞刃|勾绞|孤辰|寡宿|丧门|吊客|白虎|血刃|截路|悬针|冲|刑|害|破/.test(text)) return 'bad'
  if (/驿马|禄神|将星|国印|金舆|官|财|事业|职场/.test(text)) return 'career'
  if (/天乙|太极|文昌|福星|月德|天德|学堂|词馆|贵人|三奇|魁罡/.test(text)) return 'good'
  return 'other'
}

const shenshaByPillar = computed(() => {
  const pillarNames = ['年柱', '月柱', '日柱', '时柱']
  const groups: Record<string, (ShenshaItem & { _cat: string })[]> = {}
  const seenByPillar: Record<string, Set<string>> = {}
  for (const s of (chart.value?.shensha || [])) {
    const pillarName = pillarNames.includes(s.pillar || '') ? s.pillar! : '日柱'
    const seen = seenByPillar[pillarName] ??= new Set<string>()
    if (seen.has(s.name)) continue
    seen.add(s.name)
    const tagged = { ...s, _cat: classifyShensha(s) }
    ;(groups[pillarName] ||= []).push(tagged)
  }
  return groups
})

// 快照表神煞行：四柱 + 点选的大运 + 点选的流年，与上方列内容同源
const snapShenshaMap = computed(() => {
  const xp = xipan.value
  const map: Record<string, (ShenshaItem & { _cat: string })[]> = {}
  for (const name of ['年柱', '月柱', '日柱', '时柱']) {
    map[name] = shenshaByPillar.value[name] || []
  }
  const tag = (s: ShenshaItem) => ({ ...s, _cat: classifyShensha(s) })
  if (!xp) return map
  const ds = dayunShenshaRaw.value.find((d) => d.ganzhi === snapDayunGz.value)
  map['大运'] = (ds?.list || []).map(tag)
  const dict = xp.shenshaDict || {}
  map['流年'] = (xp.liunianShensha?.[snapLiunianGz.value] || [])
    .map((name) => ({ name, description: dict[name] || '' }))
    .map(tag)
  return map
})

function showShenshaDesc(s: ShenshaItem) {
  uni.showModal({
    title: s.name,
    content: s.description,
    showCancel: false,
    confirmText: '知道了',
  })
}

// === 十神特性 ===
const SHISHEN_INFO: Record<string, { alias?: string; positive: string; negative: string }> = {
  正官: {
    positive: '代表名誉、地位、规矩与责任感。利事业官运，为人正直守法、重视名誉、善于自我约束。',
    negative: '过旺无制则拘谨压抑、胆小怕事、依赖心重；太弱则缺乏担当、难担重任、易受人欺压。',
  },
  七杀: {
    alias: '偏官',
    positive: '代表权威、魄力、执行力与开拓精神。能掌权、闯劲足，逆境中爆发力强，宜武职、竞争与开创。',
    negative: '性烈易暴躁冲动、招惹是非官非；无制化则刑伤不断、压力过重、身心俱疲（"七杀无制祸来侵"）。',
  },
  正印: {
    positive: '代表学识、慈悲、庇护与贵人。利读书文凭、名誉声望，心地仁厚，多得长辈与母亲助力。',
    negative: '过旺则依赖惰性、行动力弱、易钻牛角尖；印重反克食伤，思想保守、不善变通表达。',
  },
  偏印: {
    alias: '枭神',
    positive: '代表领悟力、专长与冷门技艺。善钻研、有特殊才能与第六感，适技术、玄学、小众领域。',
    negative: '"枭神夺食"，易孤僻多疑、冷漠偏激；不善交际，遇食神则才华受抑、健康福泽受损。',
  },
  正财: {
    positive: '代表稳定收入、勤劳致富与务实节俭。利正业工薪、理财持家，为人踏实、重视家庭与积累。',
    negative: '太弱则财来财去、守财费力；太旺则斤斤计较、吝啬小气，反被财物所累、匮乏感强。',
  },
  偏财: {
    positive: '代表横财、机遇、社交与慷慨。利投资生意、意外之财，为人圆融、人缘佳、出手大方。',
    negative: '易投机好赌、挥霍无度；感情上多露水桃花，财来财去不稳定，重利轻义、因财生是非。',
  },
  食神: {
    positive: '代表才华、享受、口福与创造力。性温和、有艺术天赋，善表达、乐观随和，利技艺才艺。',
    negative: '过旺则贪图安逸、懒散纵欲、缺乏进取；遇枭神则"枭神夺食"，才华受抑、健康有损。',
  },
  伤官: {
    positive: '代表聪明、叛逆、创新与表达。才华外露、善辩敢突破，利艺术演艺、技术革新与自由职业。',
    negative: '"伤官见官"易傲气不服管、口舌是非；叛逆过激、轻视礼法，女命多不利夫星、感情波折。',
  },
  比肩: {
    positive: '代表同辈、朋友、合作与自立。重情义、有担当、能互助，利合伙团队，独立自主不依附。',
    negative: '"比劫夺财"易破财被分利；固执己见、争强好胜，朋友同辈反成拖累、合作生嫌隙。',
  },
  劫财: {
    positive: '代表行动力、义气与人际拓展。热情主动、善交际、乐于助人，利开拓人脉、江湖义气。',
    negative: '"劫财夺财"最甚，易破财被借被坑；冲动挥霍、争风吃醋，男命多不利财运与感情。',
  },
}

function isShishen(name?: string): boolean {
  return !!name && name !== '—' && Object.prototype.hasOwnProperty.call(SHISHEN_INFO, name)
}

const shishenModal = ref<{ name: string; positive: string; negative: string } | null>(null)
function showShishenInfo(name?: string) {
  if (!isShishen(name)) return
  const info = SHISHEN_INFO[name as string]
  const alias = info.alias ? `（又称${info.alias}）` : ''
  shishenModal.value = { name: `${name}${alias}`, positive: info.positive, negative: info.negative }
}
function closeShishenModal() {
  shishenModal.value = null
}

// === 大运/流年详情浮层 ===
const selectedDetail = ref<DayunItem | LiuNianItem | null>(null)
const activeShenshaName = ref('')
const activeShenshaDesc = ref('')
const openDetail = (d: DayunItem | LiuNianItem) => {
  selectedDetail.value = d
  activeShenshaName.value = ''
  activeShenshaDesc.value = ''
}
const closeDetail = () => {
  selectedDetail.value = null
  activeShenshaName.value = ''
  activeShenshaDesc.value = ''
}
const toggleShenshaDesc = (name: string, desc: string) => {
  if (activeShenshaName.value === name) {
    activeShenshaName.value = ''
    activeShenshaDesc.value = ''
  } else {
    activeShenshaName.value = name
    activeShenshaDesc.value = desc
  }
}
const detailSubtitle = computed(() => {
  const d = selectedDetail.value
  if (!d) return ''
  if ('startYear' in d && d.startYear) {
    return `${d.startYear}-${d.endYear || d.startYear + 9} · ${d.startAge}-${d.endAge || d.startAge + 9}岁`
  }
  if ('age' in d && (d as any).age) {
    const l = d as LiuNianItem
    return `${l.year}年 · ${l.age}虚岁${l.dayun ? ' · 所在大运 ' + l.dayun : ''}`
  }
  return ''
})

// === 复制命盘文本 ===
const copied = ref(false)
let copyTimer: ReturnType<typeof setTimeout> | null = null

function buildChartText(): string {
  const lines: string[] = ['命盘详情']
  if (birthTime.value) lines.push(`出生：${birthTime.value} ${gender.value}`)
  pillars.value.forEach((p) => {
    lines.push(`${p.name}: ${p.ganzhi} (${p.nayin})`)
    const parts: string[] = []
    if (p.shishenGan) parts.push(`主星=${p.shishenGan}`)
    if (p.changsheng) parts.push(`星运=${p.changsheng}`)
    if (p.zizuo) parts.push(`自坐=${p.zizuo}`)
    if (p.xunkong) parts.push(`空亡=${p.xunkong}`)
    if (p.hiddenStems?.length) parts.push(`藏干=${p.hiddenStems.join('')}`)
    if (p.shishenZhi?.length) parts.push(`副星=${p.shishenZhi.join('')}`)
    if (parts.length) lines.push('  ' + parts.join('，'))
  })
  const xp = xipan.value
  if (xp) {
    lines.push('', `【起运】${xp.qiyun.after} · ${xp.qiyun.direction}`)
    lines.push(`交运 ${xp.qiyun.startDate} · ${xp.qiyun.jieqi}后${xp.qiyun.daysAfterJieqi}天 · 逢${xp.qiyun.gan}年交运`)
    lines.push('', '【大运】')
    xp.dayun.forEach((d) => lines.push(`${d.startYear}-${d.endYear}（${d.startAge}-${d.endAge}岁） ${d.ganzhi}${d.shishen ? ' ' + d.shishen : ''}`))
    lines.push('', '【流年】')
    xp.liunian.forEach((l) => lines.push(`${l.year} ${l.ganzhi} ${l.shishen}（${l.age}岁${l.xiaoyun ? ' 小运' + l.xiaoyun : ''}）`))
    lines.push('', '【流月】')
    xp.liuyue.filter((m) => m.year === selectedYear.value).forEach((m) => lines.push(`${m.jieqi} ${m.date} ${m.ganzhi} ${m.shishen}`))
  }
  return lines.join('\n')
}

function copyChartText() {
  const text = buildChartText()
  uni.setClipboardData({
    data: text,
    success: () => {
      copied.value = true
      if (copyTimer) clearTimeout(copyTimer)
      copyTimer = setTimeout(() => { copied.value = false }, 1600)
    },
  })
}

// === 报告 ===
const reportContent = ref('')
const reportLoading = ref(false)

function handleDownloadPdf() {
  if (!birthTime.value || !gender.value) {
    uni.showToast({ title: '缺少出生信息', icon: 'none' })
    return
  }
  uni.showToast({ title: '正在生成 PDF，请稍候', icon: 'none', duration: 2000 })
  downloadReport(birthTime.value, gender.value)
}

function downloadFullPdf() {
  if (!birthTime.value || !gender.value) {
    uni.showToast({ title: '缺少出生信息', icon: 'none' })
    return
  }
  uni.showToast({ title: '正在生成完整 PDF，请稍候', icon: 'none', duration: 2000 })
  downloadFullReportPdf(birthTime.value, gender.value)
}

async function generateReport() {
  if (!birthTime.value || !gender.value || reportLoading.value) return
  reportLoading.value = true
  reportContent.value = ''
  uni.showToast({ title: '正在生成完整报告，请稍候', icon: 'none', duration: 2000 })
  try {
    const res = await generateFullReport(birthTime.value, gender.value)
    reportContent.value = (res as any).content || ''
    uni.showToast({ title: '完整报告生成完成', icon: 'success' })
  } catch (e: any) {
    reportContent.value = `报告生成失败：${e?.message || '请稍后重试'}`
    uni.showToast({ title: '完整报告生成失败', icon: 'none' })
  } finally {
    reportLoading.value = false
  }
}

function goBack() {
  const pages = getCurrentPages()
  if (pages.length > 1) uni.navigateBack()
  else uni.switchTab({ url: '/pages/xianzhi/index' })
}

/** 带同一套盘面参数进 K 线页：流派与经度必须一起带，否则两条曲线口径不一致 */
function goKline() {
  const q = `birth_time=${encodeURIComponent(birthTime.value)}&gender=${encodeURIComponent(gender.value)}` +
    `&sect=${chartSect.value}&yun_sect=${chartYunSect.value}`
  const lon = chartLongitude.value ? `&longitude=${chartLongitude.value}` : ''
  uni.navigateTo({ url: `/pages/kline/index?${q}${lon}` })
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
  const sect = Number(options.sect || 2) || 2
  const yunSect = Number(options.yun_sect || 1) || 1
  const longitude = Number(options.longitude || 0) || undefined
  // 记下来供后续 /relations 调用复用（同一盘面同一流派）
  chartSect.value = sect
  chartYunSect.value = yunSect
  chartLongitude.value = longitude
  getChart(birthTime.value, gender.value, sect, yunSect, longitude)
    .then((data) => {
      chart.value = data
      initXipanSelection()
      // 初次进入：直接用 /chart 已算好的那一组（对应"今天"），避免白跑一次接口
      relations.value = data.xipan?.relations || null
      relationsKey.value = currentRelationsKey()
    })
    .catch(() => { chart.value = null })
    .finally(() => { loading.value = false })
})
</script>

<style lang="scss" scoped>
.display-font { font-family: $font-family-display; }

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
  justify-content: space-between;
  height: 88rpx;
  padding: 0 24rpx;
}
.nav-back {
  font-size: 30rpx;
  color: $color-ink-light;
  padding: 8rpx 12rpx;
}
.nav-title {
  font-size: 34rpx;
  font-weight: 600;
  color: $color-ink;
  letter-spacing: 6rpx;
}
.nav-copy {
  font-size: 24rpx;
  color: $color-vermilion;
  padding: 8rpx 16rpx;
  border: 1rpx solid rgba(184, 72, 60, 0.35);
  border-radius: 10rpx;
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
.page-state.small { padding: 40rpx 24rpx; font-size: 26rpx; display: block; }

.tab-bar {
  flex-shrink: 0;
  background: $color-paper-warm;
  border-bottom: 1rpx solid $color-border;
  white-space: nowrap;
}
.tab-row { display: flex; padding: 0 12rpx; }
.tab-btn {
  flex-shrink: 0;
  padding: 14rpx 28rpx 12rpx;
  font-size: 28rpx;
  color: $color-ink-light;
  position: relative;
}
.tab-btn.tab-active {
  color: $color-vermilion;
  font-weight: 600;
}
.tab-btn.tab-active::after {
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

/* height:0 + flex:1 + min-height:0：把高度交给 flex 算法。
   小程序里 flex 子项默认 min-height:auto，会被内容撑到全高，scroll-view 自身没有
   可滚余量（表现为一直接着页面在滚、内部 scroll-y 不生效）。 */
.page-body { flex: 1; height: 0; min-height: 0; padding: 6rpx 28rpx 0; box-sizing: border-box; }
.section { margin-bottom: 32rpx; }
.section.inner { margin-bottom: 36rpx; }
/* 表格贴顶：无标题的首个 section 不留上间距 */
.section-flush { margin-top: 0; }

/* 外链 tab：点了跳走，故不给选中态，仅用主色区分「可点开」 */
.tab-btn.tab-link { color: $color-primary; }

.section-title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 20rpx;
  padding-bottom: 12rpx;
  border-bottom: 1rpx solid $color-border;
}
.section-title.flat { border-bottom: none; padding-bottom: 0; margin-bottom: 0; }
.section-title.flat::before { bottom: 0; }
.gong-info { font-size: 24rpx; color: $color-ink-light; }
.gong-summary { margin: 4rpx 0 18rpx; text-align: right; font-size: 28rpx; font-weight: 600; color: $color-primary; letter-spacing: 1rpx; line-height: 1.6; }
/* 基本信息：日主/调候文字（放大版） */
.basic-row { margin-top: 10rpx; }
.basic-info { font-size: 30rpx; color: $color-ink-light; line-height: 1.6; }
.basic-info-main { font-size: 32rpx; color: $color-ink; font-weight: 600; }
/* 起运信息（放大版） */
.qiyun-row { margin-top: 4rpx; }
.qiyun-tag { font-size: 26rpx; color: $color-vermilion; font-weight: 600; letter-spacing: 2rpx; }
.qiyun-after { font-size: 32rpx; color: $color-ink; font-weight: 600; line-height: 1.4; }
.qiyun-sub { font-size: 26rpx; color: $color-ink-light; line-height: 1.6; }
.section-title {
  display: block;
  font-size: 30rpx;
  color: $color-ink;
  letter-spacing: 6rpx;
  font-weight: 600;
  margin-bottom: 20rpx;
  padding-bottom: 12rpx;
  border-bottom: 1rpx solid $color-border;
  position: relative;
}
.section-title::before {
  content: '';
  position: absolute;
  left: 0;
  bottom: 12rpx;
  width: 6rpx;
  height: 24rpx;
  background: $color-vermilion;
  border-radius: 3rpx;
}

/* 四柱表格 */
.bazi-table {
  display: flex;
  flex-direction: column;
  border: 1rpx solid $color-border;
  border-radius: 12rpx;
  overflow: hidden;
  margin-bottom: 8rpx;
}
.bt-row {
  display: flex;
  flex-direction: row;
  border-bottom: 1rpx solid $color-border;
}
.bt-row:last-child { border-bottom: none; }
.bt-head { background: $color-paper-warm; }
.bt-cell {
  flex: 1; padding: 10rpx 4rpx; text-align: center; font-size: 26rpx; color: $color-ink;
  display: flex; align-items: center; justify-content: center;
  border-right: 1rpx solid $color-border; box-sizing: border-box; min-height: 0;
}
.bt-cell:last-child { border-right: none; }
.bt-label { flex: 0 0 80rpx; font-size: 26rpx; color: $color-ink-light; background: rgba(0,0,0,0.03); font-weight: 500; }
.bt-col-head { font-size: 26rpx; font-weight: 600; color: $color-ink; letter-spacing: 2px; }
.bt-day { background: rgba(184, 72, 60, 0.06); }
.bt-head .bt-day { background: rgba(184, 72, 60, 0.1); }
.bt-gan { font-size: 48rpx; font-weight: bold; font-family: $font-family-display; }
.bt-zhi { font-size: 48rpx; font-family: $font-family-display; }
.bt-multi { flex-direction: column; gap: 2rpx; padding: 8rpx 4rpx; }
.bt-cang { font-size: 26rpx; font-weight: 600; line-height: 1.5; }
.bt-fu { font-size: 26rpx; color: $color-ink-light; line-height: 1.5; }
.bt-shishen { font-size: 26rpx; color: $color-ink; }
.bt-shishen-tag { font-size: 26rpx; color: $color-ink; padding: 2rpx 0; line-height: 1.5; transition: transform 0.15s, opacity 0.15s; }
.bt-shishen-tag:active { transform: scale(0.95); opacity: 0.6; }
.bt-fu-click { color: $color-ink; transition: opacity 0.15s; }
.bt-fu-click:active { opacity: 0.6; }


/* 命盘六列：当前大运/流年列高亮 */
.bt-cur-head { background: rgba(212, 175, 55, 0.18); color: #8a6d3b; font-weight: 700; }
.bt-day-master { font-size: 30rpx; font-weight: 700; color: $color-vermilion; font-family: $font-family-display; }
.bt-cs { font-size: 26rpx; color: $color-ink; }
.bt-nayin { font-size: 24rpx; color: $color-ink-light; }

/* 神煞分组行 */
.ss-row { display: flex; align-items: flex-start; gap: 16rpx; padding: 12rpx 0; border-bottom: 1rpx dashed $color-border; }
.ss-row:last-child { border-bottom: none; }
.ss-gz { flex: 0 0 88rpx; font-size: 26rpx; font-weight: 700; color: $color-ink; letter-spacing: 2rpx; padding-top: 6rpx; }
.ss-gz-wide { flex: 0 0 210rpx; font-size: 24rpx; }
.ss-gz-cur { color: $color-vermilion; }
.ss-list { flex: 1; display: flex; flex-wrap: wrap; gap: 10rpx; }
/* 大运神煞：干支 + 年份区间两行标签 */
.ss-gz-col { flex: 0 0 124rpx; display: flex; flex-direction: column; gap: 2rpx; padding-top: 6rpx; }
.ss-gz-main { font-size: 26rpx; font-weight: 700; color: $color-ink; letter-spacing: 2rpx; }
.ss-gz-sub { font-size: 18rpx; color: $color-ink-light; }

/* 岁运 / 原局分析：左标签 + 关系标签流 */
.an-row { display: flex; align-items: flex-start; gap: 16rpx; padding: 12rpx 0; border-bottom: 1rpx dashed $color-border; }
.an-row:last-child { border-bottom: none; }
.an-label { flex: 0 0 72rpx; font-size: 24rpx; color: $color-ink-light; padding-top: 6rpx; }
.an-tags { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; gap: 10rpx; }
.an-tag {
  font-size: 22rpx; line-height: 1.5; padding: 4rpx 12rpx; border-radius: 8rpx;
  color: $color-ink; background: $color-paper-warm; border: 1rpx solid $color-border;
}

/* 神煞按柱竖向排列：4 列网格 */
.ss-empty { font-size: 22rpx; color: $color-ink-lighter; padding: 6rpx 0; }
.ss-tag { font-size: 22rpx; padding: 4rpx 14rpx; border-radius: 8rpx; line-height: 1.5; color: #718096; background: rgba(113,128,150,0.1); transition: transform 0.15s, opacity 0.15s; }
.ss-tag:active { opacity: 0.7; transform: scale(0.96); }
.ss-good { color: #38a169; background: rgba(56,161,105,0.1); }
.ss-bad { color: #c53030; background: rgba(197,48,48,0.1); }
.ss-love { color: #b83280; background: rgba(184,50,128,0.1); }
.ss-career { color: #2b6cb0; background: rgba(43,108,176,0.1); }
.ss-other { color: #718096; background: rgba(113,128,150,0.1); }
.ss-cur-row { background: rgba(212,175,55,0.06); border-radius: 10rpx; padding: 8rpx 4rpx; }
.ss-toggle { font-size: 22rpx; color: $color-vermilion; padding: 4rpx 8rpx; }

/* 细盘命盘大表：标签列 + 四柱 + 大运 + 流年，一屏放下不横滑 */
.pd-table { border: 1rpx solid $color-border; border-radius: 12rpx; overflow: hidden; background: $color-bg-card; }
.pd-row { display: flex; border-bottom: 1rpx solid $color-border; }
.pd-row:last-child { border-bottom: none; }
.pd-head { background: $color-paper-warm; }
.pd-cell {
  flex: 1; min-width: 0; box-sizing: border-box;
  display: flex; align-items: center; justify-content: center;
  padding: 12rpx 2rpx; font-size: 22rpx; color: $color-ink;
  border-right: 1rpx solid $color-border;
}
.pd-cell:last-child { border-right: none; }
.pd-label { flex: 0 0 76rpx; font-size: 22rpx; color: $color-ink-light; background: rgba(0, 0, 0, 0.03); }
.pd-col-head { font-size: 24rpx; font-weight: 600; color: $color-ink; letter-spacing: 2rpx; padding: 14rpx 2rpx; }
.pd-cur-head { color: #8a6d3b; font-weight: 700; }
.pd-day-master { font-size: 26rpx; font-weight: 700; color: $color-vermilion; font-family: $font-family-display; }
.pd-shishen { font-size: 22rpx; color: $color-ink; line-height: 1.4; }
.pd-click { transition: opacity 0.15s; }
.pd-click:active { opacity: 0.6; }
.pd-gan { font-size: 44rpx; font-weight: bold; font-family: $font-family-display; line-height: 1.25; }
.pd-stack { flex-direction: column; gap: 2rpx; padding: 10rpx 2rpx; }
.pd-cang-row { display: flex; flex-direction: row; align-items: baseline; justify-content: center; }
.pd-cang { font-size: 24rpx; font-weight: 600; line-height: 1.5; }
.pd-cang-ss { font-size: 20rpx; color: $color-ink-light; line-height: 1.5; margin-left: 2rpx; }
.pd-text { font-size: 22rpx; color: $color-ink; }
/* 神煞 tag 在窄列里竖排：只改尺寸，配色交给 .ss-good/.ss-bad 等 */
.pd-ss-tag { font-size: 20rpx; line-height: 1.45; padding: 2rpx 4rpx; border-radius: 6rpx; }

/* 岁运横条：大运 / 流年 / 流月，同一 grid 保证各行列对齐 */
.strip-hint-row { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 12rpx; padding: 0 2rpx; }
.strip-ctx { font-size: 24rpx; color: $color-ink; font-weight: 600; }
.strip-hint { font-size: 20rpx; color: $color-ink-light; }

/* 横条容器：左右布局，标签固定 + 内容滚动 */
.strip-container {
  display: flex;
  box-sizing: border-box;
  width: 100%;
  border: 1rpx solid $color-border;
  border-radius: 12rpx;
  overflow: hidden;
  background: $color-border;
}
.strip-labels-fixed {
  flex-shrink: 0;
  width: 72rpx;
  height: 100%;
  background: $color-paper-warm;
  border-right: 1rpx solid $color-border;
  z-index: 10;
}
.strip-labels-grid {
  display: grid;
  gap: 1rpx;
}
.strip-scroll-content {
  flex: 1;
  min-width: 0;
  height: 100%;
  white-space: nowrap;
}
.strip-grid {
  display: grid; gap: 1rpx;
  overflow: hidden;
  background: $color-border;
}
.strip-cell {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  box-sizing: border-box; min-width: 0; padding: 8rpx 2rpx;
  background: $color-bg-card;
}
.strip-label { font-size: 22rpx; color: $color-ink-light; background: $color-paper-warm; letter-spacing: 1rpx; }
.strip-click { transition: opacity 0.15s; }
.strip-click:active { opacity: 0.7; }
.strip-cur { background: rgba(212, 175, 55, 0.16); }
.strip-sel { background: rgba(184, 72, 60, 0.1); }
.sc-year { font-size: 24rpx; font-weight: 600; color: $color-ink; line-height: 1.35; }
.sc-jie { font-size: 22rpx; font-weight: 600; color: $color-ink; line-height: 1.35; }
.sc-age { font-size: 20rpx; color: $color-ink-light; line-height: 1.35; white-space: nowrap; }
.sc-gz { display: flex; flex-direction: row; align-items: baseline; justify-content: center; }
.sc-gan { font-size: 38rpx; font-weight: bold; font-family: $font-family-display; line-height: 1.3; }
.sc-ss { font-size: 20rpx; color: $color-ink-light; margin-left: 2rpx; }
.sc-tongxian { color: $color-ink; }
.sc-cs { font-size: 24rpx; color: $color-ink; }
.sc-xy { font-size: 24rpx; color: $color-vermilion; }
.strip-cur .sc-year, .strip-cur .sc-jie, .strip-cur .sc-cs { color: #8a6d3b; font-weight: 600; }
.strip-sel .sc-year, .strip-sel .sc-jie { color: $color-vermilion; font-weight: 700; }

/* 五行 */
.wuxing-grid { display: flex; justify-content: space-around; align-items: flex-end; height: 220rpx; }
.wuxing-item { display: flex; flex-direction: column; align-items: center; width: 18%; }
.wuxing-bar-container { width: 100%; height: 140rpx; display: flex; align-items: flex-end; background: $color-paper-warm; border-radius: 8rpx 8rpx 0 0; overflow: hidden; }
.wuxing-bar { width: 100%; border-radius: 8rpx 8rpx 0 0; min-height: 6rpx; }
.wuxing-label { font-size: 30rpx; font-weight: bold; margin-top: 8rpx; }
.wuxing-count { font-size: 26rpx; color: $color-ink-light; }

/* 大运 */

.warning-list { display: flex; flex-direction: column; gap: 8rpx; margin-top: 12rpx; }
.warning-item { padding: 12rpx 14rpx; background: $color-paper-warm; border: 1rpx solid $color-border; border-left: 4rpx solid $state-warning; border-radius: 8rpx; color: $color-ink; font-size: 26rpx; line-height: 1.5; }

/* === 细盘（时间层级） === */
/* 专业细盘顶部：起运 + 岁数/司令 同一行 */
.xp-topbar {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 16rpx;
  background: $color-paper-warm;
  border: 1rpx solid $color-border;
  border-left: 6rpx solid $color-vermilion;
  border-radius: 12rpx;
  padding: 18rpx 20rpx;
  margin-bottom: 32rpx;
}
.xp-top-qiyun { display: flex; flex-direction: column; gap: 6rpx; }
.xp-top-tag {
  align-self: flex-start;
  font-size: 22rpx; color: $color-vermilion; font-weight: 600; letter-spacing: 2rpx;
  padding: 2rpx 12rpx; border: 1rpx solid rgba(184, 72, 60, 0.4); border-radius: 8rpx;
  margin-bottom: 4rpx;
}
.xp-top-after { font-size: 30rpx; color: $color-ink; font-weight: 700; line-height: 1.3; }
.xp-top-sub { font-size: 22rpx; color: $color-ink-light; line-height: 1.5; }
.xp-top-meta { display: flex; flex-direction: column; align-items: flex-end; justify-content: center; text-align: right; gap: 6rpx; }
.xp-top-age { font-size: 26rpx; color: $color-ink; font-weight: 600; }
.xp-top-siling { font-size: 24rpx; color: #8a6d3b; }

/* 当前快照已并入 .pd-table 命盘大表 */

.xp-state-row { display: flex; gap: 16rpx; margin-bottom: 32rpx; }
.xp-state-block { flex: 1; min-width: 0; background: $color-bg-card; border: 1rpx solid $color-border; border-radius: 12rpx; padding: 16rpx 18rpx; box-sizing: border-box; }
.xp-state-title { display: block; font-size: 24rpx; color: $color-ink-light; letter-spacing: 4rpx; margin-bottom: 14rpx; }
.xp-state-items { display: flex; flex-wrap: wrap; gap: 10rpx; }
.xp-state-item { font-size: 26rpx; padding: 4rpx 16rpx; border-radius: 8rpx; border: 1rpx solid $color-border; color: $color-ink; }
.xs-0 { color: #c53030; border-color: rgba(197,48,48,0.35); }
.xs-1 { color: #b7791f; border-color: rgba(183,121,31,0.35); }
.xs-2 { color: #2b6cb0; border-color: rgba(43,108,176,0.35); }
.xs-3 { color: #6b46c1; border-color: rgba(107,70,193,0.35); }
.xs-4 { color: #718096; border-color: rgba(113,128,150,0.35); }
.xp-siling { font-size: 30rpx; color: $color-vermilion; font-weight: 700; }
.xp-siling-detail { display: block; font-size: 22rpx; color: $color-ink-light; margin-top: 10rpx; line-height: 1.6; }

.xp-dayun-scroll { width: 100%; white-space: nowrap; }
.xp-dayun-strip { display: inline-flex; gap: 14rpx; padding: 4rpx 2rpx 8rpx; }
.xp-dayun-chip.active { border-color: $color-vermilion; background: rgba(184, 72, 60, 0.07); }
.xp-dayun-chip.now { border-color: rgba(184, 72, 60, 0.5); }
.xp-dayun-chip.active .xp-dy-gz { color: $color-vermilion; }

.xp-ln-chip.active { border-color: $color-vermilion; background: rgba(184, 72, 60, 0.07); }
.xp-ln-chip.now { border-color: rgba(184, 72, 60, 0.5); }
.xp-ln-chip.active .xp-ln-gz { color: $color-vermilion; }

.xipan-note {
  padding: 14rpx 16rpx;
  background: $color-paper-warm;
  border: 1rpx dashed $color-border;
  border-radius: 10rpx;
  color: $color-ink-light;
  font-size: 22rpx;
  line-height: 1.55;
}

/* 报告 */
.report-loading { padding: 32rpx; text-align: center; color: $color-ink-light; font-size: 30rpx; letter-spacing: 2rpx; }
.report-placeholder { padding: 32rpx; text-align: center; color: $color-ink-lighter; font-size: 28rpx; }
.report-content { background: $color-paper-warm; border: 1rpx solid $color-border; border-radius: 12rpx; padding: 24rpx; }

/* 底部操作栏 */
.page-footer {
  flex-shrink: 0;
  display: flex;
  gap: 14rpx;
  padding: 18rpx 24rpx calc(18rpx + env(safe-area-inset-bottom));
  border-top: 1rpx solid $color-border;
  background: $color-paper-warm;
}
.fbtn {
  flex: 1; min-width: 0; text-align: center;
  padding: 18rpx 12rpx;
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-radius: 16rpx;
  font-size: 26rpx;
  color: $color-ink;
  letter-spacing: 2rpx;
  box-sizing: border-box;
}
.fbtn-primary { background: $color-vermilion; color: $color-paper; border-color: $color-vermilion; }
.fbtn.disabled { opacity: 0.4; }
.bottom-spacer { height: 40rpx; }

/* 大运/流年详情浮层 */
.detail-mask {
  position: fixed; left: 0; right: 0; top: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 999;
  display: flex; align-items: center; justify-content: center;
  padding: 40rpx; box-sizing: border-box;
}
.detail-card {
  width: 100%; max-width: 640rpx; max-height: 80vh;
  background: linear-gradient(135deg, $color-paper, $color-bg-card);
  border: 1rpx solid $color-border;
  border-radius: 20rpx;
  padding: 28rpx 28rpx 24rpx;
  box-shadow: 0 10rpx 40rpx rgba(0, 0, 0, 0.4);
  box-sizing: border-box;
  overflow-y: auto;
}
.detail-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6rpx; }
.detail-title { font-size: 44rpx; font-weight: 700; color: $color-primary; letter-spacing: 6rpx; font-family: $font-family-display; }
.detail-close { font-size: 32rpx; color: $color-ink-light; padding: 8rpx 16rpx; }
.detail-sub { display: block; font-size: 22rpx; color: $color-ink-light; text-align: center; letter-spacing: 2rpx; margin-bottom: 20rpx; }
.detail-grid { background: $color-paper-warm; border: 1rpx solid $color-border; border-radius: 12rpx; padding: 4rpx 16rpx; margin-bottom: 20rpx; }
.detail-row { display: flex; align-items: center; justify-content: space-between; padding: 16rpx 0; border-bottom: 1rpx solid $color-border; }
.detail-row:last-child { border-bottom: none; }
.detail-label { font-size: 24rpx; color: $color-ink-light; letter-spacing: 2rpx; }
.detail-value { font-size: 26rpx; color: $color-ink; font-weight: 600; font-family: $font-family-display; max-width: 60%; text-align: right; }
.detail-shensha-block { margin-bottom: 20rpx; }
.detail-shensha-title { display: block; font-size: 24rpx; color: $color-ink-light; letter-spacing: 2rpx; margin-bottom: 12rpx; }
.detail-shensha-hint { font-size: 20rpx; }
.detail-shensha-tags { display: flex; flex-wrap: wrap; gap: 10rpx; }
.detail-shensha-tag { display: inline-block; font-size: 22rpx; padding: 6rpx 16rpx; background: rgba(212, 175, 55, 0.1); border: 1rpx solid rgba(212, 175, 55, 0.3); border-radius: 8rpx; color: $color-primary; letter-spacing: 1rpx; }
.detail-shensha-tag.active { background: rgba(212, 175, 55, 0.25); border-color: $color-primary; font-weight: 600; }
.detail-shensha-desc { margin-top: 12rpx; padding: 12rpx 16rpx; background: $color-paper-warm; border: 1rpx solid $color-border; border-left: 4rpx solid $color-primary; border-radius: 8rpx; }
.detail-shensha-desc-name { display: block; font-size: 24rpx; color: $color-vermilion; font-weight: 600; margin-bottom: 4rpx; }
.detail-shensha-desc-text { display: block; font-size: 24rpx; color: $color-ink; line-height: 1.6; }
.detail-actions { display: flex; justify-content: center; }
.detail-action-btn { padding: 14rpx 56rpx; background: $color-bg-card; border: 1rpx solid $color-border; border-radius: 12rpx; font-size: 26rpx; color: $color-ink-light; letter-spacing: 2rpx; }

/* 十神浮层 */
.shishen-mask { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.shishen-card { width: 78%; max-width: 620rpx; max-height: 78%; background: $color-paper; border-radius: 20rpx; box-shadow: 0 12rpx 40rpx rgba(0, 0, 0, 0.25); display: flex; flex-direction: column; overflow: hidden; }
.shishen-header { display: flex; align-items: center; justify-content: space-between; padding: 28rpx 32rpx 16rpx; border-bottom: 1rpx solid rgba(184, 134, 11, 0.15); }
.shishen-title { font-size: 40rpx; font-weight: 600; color: $color-ink; flex: 1; text-align: center; }
.shishen-close { font-size: 36rpx; color: $color-ink-light; padding: 0 8rpx; }
.shishen-body { padding: 24rpx 32rpx 32rpx; overflow-y: auto; }
.shishen-section { margin-bottom: 20rpx; }
.shishen-section:last-child { margin-bottom: 0; }
.shishen-label { display: block; font-size: 32rpx; font-weight: 600; color: $color-ink; font-family: $font-family-display; margin-bottom: 12rpx; letter-spacing: 2rpx; text-align: center; }
.shishen-text { display: block; font-size: 27rpx; color: $color-ink; line-height: 1.85; white-space: pre-wrap; word-break: break-all; }
</style>