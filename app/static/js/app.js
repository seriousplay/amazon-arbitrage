/**
 * Amazon Arbitrage Scout - Frontend Application
 * Modular JavaScript with proper error handling and organization
 */

// ═══════════════════════════════════════════════════════
// Configuration Constants
// ═══════════════════════════════════════════════════════

const CONFIG = Object.freeze({
  API_BASE: '/api/v1',
  POLL_INTERVAL_MS: 1800,
  POLL_TASK_INTERVAL_MS: 2000,
  POLL_TASK_MAX_ITERATIONS: 90,
  ERROR_THRESHOLD_MS: 15000,
  DEFAULT_SCAN_COUNT: 15,
  MAX_RESULTS_DISPLAY: 15,
  ROBOT_COLORS: [
    '#5dade2', '#f5b041', '#58d68d', '#ec7063', '#af7ac5',
    '#f1948a', '#85c1e9', '#f8c471', '#82e0aa', '#a3e4d7',
    '#f0b27a', '#7fb3d8', '#d2b4de', '#a9dfbf', '#fad7a0',
    '#aed6f1', '#f9e79f', '#d5dbdb', '#aab7b8', '#edbb99',
  ],
});

// ═══════════════════════════════════════════════════════
// Global State
// ═══════════════════════════════════════════════════════

const state = {
  allCats: [],
  allTaskIds: [],
  allResults: [],
  rulesCache: null,
  scanPollId: null,
  selectedCats: new Set(),
  scheduleEnabled: false,
};

// ═══════════════════════════════════════════════════════
// Utility Functions
// ═══════════════════════════════════════════════════════

/**
 * DOM helper - get element by ID
 * @param {string} id - Element ID
 * @returns {HTMLElement|null}
 */
function $(id) {
  return document.getElementById(id);
}

/**
 * Format number with fixed decimal places
 * @param {number} n - Number to format
 * @param {number} d - Decimal places (default: 1)
 * @returns {string}
 */
function formatNumber(n, d = 1) {
  return Number(n || 0).toFixed(d);
}

/**
 * Null-safe value renderer with fallback
 * @param {*} v - Value to render
 * @param {string} f - Fallback value
 * @returns {string}
 */
function renderValue(v, f = '--') {
  return v != null && v !== undefined ? v : f;
}

/**
 * Escape HTML to prevent XSS
 * @param {string} s - String to escape
 * @returns {string}
 */
function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

// ═══════════════════════════════════════════════════════
// API Client with Error Handling
// ═══════════════════════════════════════════════════════

/**
 * Custom API Error class
 */
class APIError extends Error {
  /**
   * @param {number} status - HTTP status code
   * @param {string} body - Response body
   */
  constructor(status, body) {
    super(`API Error ${status}: ${body}`);
    this.name = 'APIError';
    this.status = status;
    this.body = body;
  }
}

/**
 * API client with typed methods
 */
const API = {
  /**
   * Make a generic API request
   * @param {string} path - API endpoint path
   * @param {RequestInit} options - Fetch options
   * @returns {Promise<any>}
   * @throws {APIError} If response is not OK
   */
  async request(path, options = {}) {
    const url = `${CONFIG.API_BASE}${path}`;
    const response = await fetch(url, options);
    if (!response.ok) {
      const text = await response.text();
      throw new APIError(response.status, text || response.statusText);
    }
    return response.json();
  },

  /**
   * GET /results/categories - Get available product categories
   * @returns {Promise<{categories: Array}>}
   */
  async getCategories() {
    return this.request('/results/categories');
  },

  /**
   * POST /scan/discover-only - Start Amazon discovery phase
   * @param {string} category - Category name
   * @param {number} maxProducts - Max products to discover
   * @param {string} [bsrUrl] - Optional BSR URL
   * @returns {Promise<{task_id: string, phase: string}>}
   */
  async startDiscover(category, maxProducts, bsrUrl = null) {
    const params = new URLSearchParams({ category, max_products: maxProducts });
    if (bsrUrl) params.append('bsr_url', bsrUrl);
    return this.request(`/scan/discover-only?${params}`, { method: 'POST' });
  },

  /**
   * GET /results/task/{taskId} - Get task status and results
   * @param {string} taskId - Task ID
   * @returns {Promise<object>}
   */
  async getTask(taskId) {
    return this.request(`/results/task/${taskId}`);
  },

  /**
   * POST /scan/cancel-all - Cancel all running scan tasks
   * @returns {Promise<{success: boolean, cancelled: number}>}
   */
  async cancelAll() {
    return this.request('/scan/cancel-all', { method: 'POST' });
  },

  /**
   * POST /scan/{taskId}/match-now - Start 1688 matching for a task
   * @param {string} taskId - Task ID
   * @returns {Promise<{success: boolean}>}
   */
  async matchNow(taskId) {
    return this.request(`/scan/${taskId}/match-now`, { method: 'POST' });
  },

  /**
   * GET /status/login - Get 1688 login status
   * @returns {Promise<{status: string, message: string}>}
   */
  async getLoginStatus() {
    return this.request('/status/login');
  },

  /**
   * GET /scan/rules/raw - Get current filter rules
   * @returns {Promise<object>}
   */
  async getRules() {
    return this.request('/scan/rules/raw');
  },

  /**
   * GET /scan/schedule - Get scheduler configuration
   * @returns {Promise<{tasks: object, last_runs: object}>}
   */
  async getSchedule() {
    return this.request('/scan/schedule');
  },

  /**
   * POST /scan/schedule/{taskId}/toggle - Enable/disable scheduled task
   * @param {string} taskId - Task ID (e.g., 'weekly-scan')
   * @param {boolean} enabled - Enable or disable
   * @returns {Promise<{success: boolean}>}
   */
  async toggleSchedule(taskId, enabled) {
    return this.request(`/scan/schedule/${taskId}/toggle?enabled=${enabled}`, { method: 'POST' });
  },
};

// ═══════════════════════════════════════════════════════
// Robot Grid Component
// ═══════════════════════════════════════════════════════

const RobotGrid = {
  /**
   * Render robot grid for active scan tasks
   * @param {Array} tasks - Array of task info objects
   */
  render(tasks) {
    let html = `<div style="margin-bottom:8px;font-size:12px;color:var(--text2)">🎮 <b>机器人车间</b> — ${tasks.length}位机器人并行扫描中</div><div class="robot-grid">`;

    for (let i = 0; i < tasks.length; i++) {
      const t = tasks[i];
      const catName = t.cat || '未知品类';
      const state = t.error ? 'error' : 'waiting';
      const statusText = t.error ? '启动失败' : '启动中...';
      const color = CONFIG.ROBOT_COLORS[i % CONFIG.ROBOT_COLORS.length];
      const shortCat = catName.length > 16 ? catName.slice(0, 14) + '..' : catName;

      html += `<div class="robot-card state-${state}" id="robot-${i}">
        <div class="robot-concurrency" id="rc-${i}">⚡ ${t.error ? '✗' : '启动中'}</div>
        <div class="robot-face" style="border:2px solid ${color}">
          <div class="robot-eyes"><div class="robot-eye" style="background:${color}"></div><div class="robot-eye" style="background:${color}"></div></div>
          <div class="robot-mouth" style="background:${color}"></div>
        </div>
        <div class="robot-category" title="${escapeHtml(catName)}">${escapeHtml(shortCat)}</div>
        <div class="robot-progress"><div class="robot-progress-fill" id="rpf-${i}" style="width:0%"></div></div>
        <div class="robot-status" id="rs-${i}">${statusText}</div>
        <div class="robot-time" id="rt-${i}"></div>
      </div>`;
    }

    html += '</div>';
    $('mainContent').innerHTML = html;
  },

  /**
   * Update robot grid with current states
   * @param {Array} states - Array of robot state objects
   */
  update(states) {
    const activeCount = states.filter((s) => !s.done && !s.error).length;
    const doneCount = states.filter((s) => s.done).length;
    const total = states.length;

    for (let i = 0; i < states.length; i++) {
      const s = states[i];
      const card = document.getElementById(`robot-${i}`);
      if (!card) continue;

      // Update card state class
      card.className = `robot-card state-${s.status}`;

      // Update progress bar
      const pf = document.getElementById(`rpf-${i}`);
      if (pf) pf.style.width = `${s.progress}%`;

      // Update status text
      const st = document.getElementById(`rs-${i}`);
      if (st) {
        const steps = {
          waiting: '⏳ 启动中',
          scanning: s.step || '🔍 爬取',
          analyzing: s.step || '📊 分析',
          complete: '✅ 完成',
          error: '❌ 失败',
        };
        st.textContent = steps[s.status] || s.step || '...';
      }

      // Update elapsed time
      const rt = document.getElementById(`rt-${i}`);
      if (rt && s.elapsed > 0) rt.textContent = `${s.elapsed}s`;

      // Update concurrency badge
      const rc = document.getElementById(`rc-${i}`);
      if (rc) {
        if (s.status === 'scanning') rc.textContent = '🔍 爬取中';
        else if (s.status === 'analyzing') rc.textContent = '📊 分析中';
        else if (s.status === 'complete') rc.textContent = '✅ 完成';
        else if (s.status === 'error') rc.textContent = '❌ 故障';
        else rc.textContent = `⏳ 启动中 (${activeCount}运行)`;
      }

      // Update face border color for completed/error states
      const face = card.querySelector('.robot-face');
      if (face) {
        if (s.status === 'complete') face.style.borderColor = 'var(--green)';
        else if (s.status === 'scanning') face.style.borderColor = 'var(--accent)';
        else if (s.status === 'analyzing') face.style.borderColor = 'var(--purple)';
        else if (s.status === 'error') face.style.borderColor = 'var(--red)';
        else face.style.borderColor = '';
      }
    }

    // Update summary
    const summary = document.querySelector('#mainContent > div:first-child');
    if (summary) {
      summary.innerHTML = `🎮 <b>机器人车间</b> — ${doneCount}/${total} 完成 · ${activeCount} 扫描中`;
    }
  },
};

// ═══════════════════════════════════════════════════════
// Product Card Component
// ═══════════════════════════════════════════════════════

const ProductCard = {
  /**
   * Render a single product card
   * @param {object} p - Product data
   * @param {number} idx - Card index (for expand/collapse)
   * @returns {string} HTML string
   */
  render(p, idx) {
    const bs = p.breakout_score;
    const d = bs.dimensions;
    const gradeColors = {
      'S级爆款': 'var(--green)',
      'A级潜力': 'var(--accent)',
      'B级观察': 'var(--orange)',
    };
    const gc = gradeColors[bs.grade] || 'var(--text2)';
    const reasons = this._getReasons(d);
    const risk = p.risk_assessment;
    const risks = risk ? risk.risks || [] : [];
    const trend = p.trend_data;
    const dims = this._getDimensions(d);

    return `<div class="product-card ${this._getGradeClass(bs.grade)}" onclick="toggleCard(${idx})">
      <div class="product-header">
        <div class="product-title" title="${escapeHtml(p.title)}">${escapeHtml(p.title)}</div>
        <div class="product-score" style="color:${gc}">${formatNumber(bs.total, 1)}</div>
      </div>
      <div class="product-meta">
        <span>🏷️ ${bs.grade}</span>
        <span>📊 BSR #${renderValue(p.rank)}</span>
        <span>💵 ${p.price ? '$' + p.price : '--'}</span>
        <span>⭐ ${renderValue(p.rating)}</span>
        <span>💬 ${renderValue(p.review_count, 0)}评</span>
        ${p.profit_margin ? `<span>📈 ${formatNumber(p.profit_margin, 1)}%利润</span>` : ''}
        ${p.has_match ? '<span style="color:var(--green)">✅ 已匹配</span>' : '<span style="color:var(--text2)">⏳ 待匹配</span>'}
        <span style="font-size:10px;color:var(--accent);margin-left:auto">▼ 详情</span>
      </div>
      <div class="product-reason">💡 ${reasons.length ? reasons.join('；') : '数据不足'}</div>
      ${risks.length || trend ? `<div class="product-warnings">
        ${risks.map((r) => `<span class="warn-risk">⚠️ ${escapeHtml(r)}</span>`).join('')}
        ${trend && trend.matched_keyword ? `<span class="warn-trend">📊 ${escapeHtml(trend.recommendation)}</span>` : ''}
      </div>` : ''}
      <div class="dim-bars">${dims.map((dm) => `<div class="dim-bar" title="${dm.l}: ${formatNumber(dm.v, 1)}/${dm.m}"><div class="fill ${dm.c}" style="width:${(dm.v / dm.m) * 100}%"></div></div>`).join('')}</div>
      <div class="card-expand" id="expand-${idx}">
        <div class="expand-inner">
          ${this.renderDetailBasic(p)}${this.renderDetailMatch(p)}${this.renderDetailDimensions(p, bs)}${this.renderDetailRisk(p, risk)}${this.renderDetailTrend(p, trend)}${this.renderDetailRules()}
        </div>
      </div>
    </div>`;
  },

  _getGradeClass(grade) {
    return grade === 'S级爆款' ? 's-grade' : grade === 'A级潜力' ? 'a-grade' : 'b-grade';
  },

  _getReasons(d) {
    const reasons = [];
    if (d.product_fundamentals >= 15) reasons.push('产品力强（高评分+大量评论验证需求）');
    else if (d.product_fundamentals >= 10) reasons.push('产品基本面良好');
    if (d.market_demand >= 15) reasons.push('市场需求旺盛（头部BSR排名）');
    else if (d.market_demand >= 8) reasons.push('需求稳定');
    if (d.profit_potential >= 15) reasons.push('利润空间充足（1688价差显著）');
    else if (d.profit_potential >= 8) reasons.push('有盈利空间');
    if (d.competition >= 10) reasons.push('竞争格局有利（蓝海机会）');
    if (d.supply_chain >= 8) reasons.push('1688供应链成熟');
    if (d.risk >= 8) reasons.push('风险可控');
    if (d.trend >= 4) reasons.push('搜索热度上升');
    return reasons;
  },

  _getDimensions(d) {
    return [
      { v: d.product_fundamentals, m: 20, c: 'fill-green', l: '产品力' },
      { v: d.market_demand, m: 20, c: 'fill-blue', l: '需求' },
      { v: d.competition, m: 15, c: 'fill-purple', l: '竞争' },
      { v: d.profit_potential, m: 20, c: 'fill-green', l: '利润' },
      { v: d.supply_chain, m: 10, c: 'fill-blue', l: '供应链' },
      { v: d.risk, m: 10, c: d.risk >= 8 ? 'fill-green' : d.risk >= 5 ? 'fill-orange' : 'fill-red', l: '风险' },
      { v: d.trend, m: 5, c: d.trend >= 4 ? 'fill-green' : d.trend >= 3 ? 'fill-blue' : 'fill-orange', l: '趋势' },
    ];
  },

  renderDetailBasic(p) {
    return `<div class="detail-section"><h4>📋 基本信息</h4><div class="detail-grid">
      <div class="detail-item"><span class="key">ASIN</span><span class="val"><a href="https://www.amazon.com/dp/${p.asin}" target="_blank" rel="noopener">${p.asin} ↗</a></span></div>
      <div class="detail-item"><span class="key">品牌</span><span class="val">${renderValue(p.brand, '未知')}</span></div>
      <div class="detail-item"><span class="key">品类路径</span><span class="val">${renderValue(p.category_path, '未知')}</span></div>
      <div class="detail-item"><span class="key">Amazon售价</span><span class="val" style="color:var(--green)">${p.price ? '$' + p.price : '--'}</span></div>
      <div class="detail-item"><span class="key">评分</span><span class="val">⭐ ${renderValue(p.rating)}</span></div>
      <div class="detail-item"><span class="key">评论数</span><span class="val">${renderValue(p.review_count, 0)}</span></div>
      <div class="detail-item"><span class="key">BSR排名</span><span class="val">#${renderValue(p.rank)}</span></div>
      <div class="detail-item"><span class="key">利润率</span><span class="val" style="color:${p.profit_margin >= 30 ? 'var(--green)' : 'var(--orange)'}">${p.profit_margin ? formatNumber(p.profit_margin, 1) + '%' : '待匹配'}</span></div>
    </div></div>`;
  },

  renderDetailMatch(p) {
    if (!p.has_match || !p.match_score) return '';
    return `<div class="detail-section"><h4>🔗 1688 匹配详情</h4><div class="detail-grid">
      <div class="detail-item"><span class="key">匹配分</span><span class="val" style="color:${p.match_score >= 70 ? 'var(--green)' : 'var(--orange)'}">${formatNumber(p.match_score, 1)}</span></div>
      <div class="detail-item"><span class="key">预估利润</span><span class="val" style="color:var(--green)">${p.profit_margin ? formatNumber(p.profit_margin, 1) + '%' : '--'}</span></div>
    </div></div>`;
  },

  renderDetailDimensions(p, bs) {
    const d = bs.dimensions;
    const allDims = [
      { k: 'product_fundamentals', l: '产品力', v: d.product_fundamentals, m: 20, desc: '评分+评论数综合评估产品的市场验证程度', c: d.product_fundamentals >= 15 ? 'green' : d.product_fundamentals >= 10 ? 'blue' : 'orange' },
      { k: 'market_demand', l: '市场需求', v: d.market_demand, m: 20, desc: 'BSR排名反映搜索量级、评论增长率体现需求趋势', c: d.market_demand >= 15 ? 'green' : d.market_demand >= 8 ? 'blue' : 'orange' },
      { k: 'competition', l: '竞争格局', v: d.competition, m: 15, desc: 'BSR排名与评论数分布推断竞争激烈程度', c: d.competition >= 10 ? 'green' : d.competition >= 5 ? 'blue' : 'orange' },
      { k: 'profit_potential', l: '利润空间', v: d.profit_potential, m: 20, desc: 'Amazon售价与1688成本价的价差评估', c: d.profit_potential >= 15 ? 'green' : d.profit_potential >= 8 ? 'blue' : 'orange' },
      { k: 'supply_chain', l: '供应链', v: d.supply_chain, m: 10, desc: '1688匹配成功率、起订量、供应商评分', c: d.supply_chain >= 8 ? 'green' : d.supply_chain >= 5 ? 'blue' : 'orange' },
      { k: 'risk', l: '风险', v: d.risk, m: 10, desc: '商标/专利/认证/合规风险综合评估', c: d.risk >= 8 ? 'green' : d.risk >= 5 ? 'orange' : 'red' },
      { k: 'trend', l: '趋势', v: d.trend, m: 5, desc: 'Google Trends搜索热度 + 季节性 + 品类生命周期', c: d.trend >= 4 ? 'green' : d.trend >= 3 ? 'blue' : 'orange' },
    ];

    return `<div class="detail-section"><h4>📊 评分维度详解</h4>
      ${allDims.map((di) => `
        <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border)">
          <div style="width:50px;font-size:11px;font-weight:600;color:var(--${di.c})">${formatNumber(di.v, 1)}/${di.m}</div>
          <div style="flex:1"><div style="font-size:12px">${di.l}</div><div style="font-size:10px;color:var(--text2)">${di.desc}</div></div>
          <div style="width:60px;height:4px;background:var(--surface3);border-radius:2px;overflow:hidden"><div style="height:100%;background:var(--${di.c});border-radius:2px;width:${(di.v / di.m) * 100}%"></div></div>
        </div>`).join('')}
    </div>`;
  },

  renderDetailRisk(p, risk) {
    if (!risk) return '';
    const items = risk.risks || [];
    const level = risk.level || '未知';
    const levelColor = level === '低风险' ? 'low' : level === '中风险' ? 'medium' : 'high';
    return `<div class="detail-section"><h4>⚠️ 风险评估 <span class="badge badge-${levelColor}">${escapeHtml(level)}</span></h4>
      ${items.length ? items.map((r) => `<div style="padding:3px 0;font-size:12px;display:flex;gap:6px"><span style="color:var(--red)">•</span>${escapeHtml(r)}</div>`).join('') : '<div style="color:var(--text2);font-size:12px">未发现明显风险</div>'}
    </div>`;
  },

  renderDetailTrend(p, trend) {
    if (!trend) return '';
    const dirBadge = trend.direction === 'up' ? 'up' : trend.direction === 'down' ? 'down' : 'flat';
    const confBadge = trend.confidence === 'high' ? 'low' : trend.confidence === 'medium' ? 'medium' : 'high';
    return `<div class="detail-section"><h4>📈 趋势信号 <span class="badge badge-${dirBadge}">${trend.direction === 'up' ? '上升' : trend.direction === 'down' ? '下降' : '平稳'}</span></h4><div class="detail-grid">
      <div class="detail-item"><span class="key">匹配关键词</span><span class="val">${escapeHtml(trend.matched_keyword || '--')}</span></div>
      <div class="detail-item"><span class="key">热度指数</span><span class="val">${renderValue(trend.popularity)}/100</span></div>
      <div class="detail-item"><span class="key">近1月变化</span><span class="val" style="color:${trend.change_1m >= 0 ? 'var(--green)' : 'var(--red)'}">${trend.change_1m >= 0 ? '+' : ''}${formatNumber(trend.change_1m, 1)}%</span></div>
      <div class="detail-item"><span class="key">近3月变化</span><span class="val" style="color:${trend.change_3m >= 0 ? 'var(--green)' : 'var(--red)'}">${trend.change_3m >= 0 ? '+' : ''}${formatNumber(trend.change_3m, 1)}%</span></div>
      <div class="detail-item"><span class="key">近6月变化</span><span class="val" style="color:${trend.change_6m >= 0 ? 'var(--green)' : 'var(--red)'}">${trend.change_6m >= 0 ? '+' : ''}${formatNumber(trend.change_6m, 1)}%</span></div>
      <div class="detail-item"><span class="key">数据源</span><span class="val">${trend.source === 'builtin' ? '内建数据集' : trend.source === 'bsr' ? 'BSR反推' : trend.source === 'web' ? '网络搜索' : '估算'}</span></div>
      <div class="detail-item"><span class="key">置信度</span><span class="val"><span class="badge badge-${confBadge}">${trend.confidence || 'medium'}</span></span></div>
      ${trend.seasonality_peak && trend.seasonality_peak.length ? `<div class="detail-item"><span class="key">季节性高峰</span><span class="val">${trend.seasonality_peak.map((m) => m + '月').join('、')}</span></div>` : ''}
      ${trend.related_queries && trend.related_queries.length ? `<div class="detail-item"><span class="key">相关搜索词</span><span class="val" style="font-size:10px">${trend.related_queries.slice(0, 5).join(', ')}</span></div>` : ''}
    </div></div>`;
  },

  renderDetailRules() {
    if (!state.rulesCache) return '';
    return `<div class="detail-section"><h4>⚙️ 应用规则</h4>${this.renderRulesSummary(state.rulesCache)}</div>`;
  },

  renderRulesSummary(rules) {
    if (!rules || !Object.keys(rules).length) return '';
    const items = [
      ['最低售价', rules.min_price, '$'],
      ['最高售价', rules.max_price, '$'],
      ['最低评分', rules.min_rating, ''],
      ['最少评论', rules.min_reviews, ''],
      ['BSR上限', rules.max_bsr_rank, '#'],
      ['最低利润率', rules.min_profit_margin, '%'],
      ['最低价差倍率', rules.min_price_ratio, '×'],
    ];
    return items
      .map(([k, v, u]) => `<div class="rule-line"><span class="rule-pass">✓</span><span>${k}: ${v ?? '--'}${v != null ? u : ''}</span></div>`)
      .join('');
  },
};

// ═══════════════════════════════════════════════════════
// Category Management
// ═══════════════════════════════════════════════════════

const CategoryManager = {
  /**
   * Load categories from API
   */
  async load() {
    try {
      const d = await API.getCategories();
      state.allCats = d.categories || [];
      // Select all by default
      state.selectedCats = new Set(state.allCats.map((c) => c.id));
      this.renderCheckboxes();
      this.updateSummary();
    } catch (e) {
      $('catChips').textContent = '获取品类列表失败';
    }
  },

  /**
   * Render category checkboxes
   */
  renderCheckboxes() {
    if (!state.allCats.length) return;
    const grid = $('catCheckboxGrid');
    grid.innerHTML = state.allCats.map((c) => {
      const checked = state.selectedCats.has(c.id) ? 'checked' : '';
      const catId = c.id.replace(/[^a-z0-9-]/g, '');
      return `<label style="display:flex;align-items:center;gap:5px;padding:3px 5px;cursor:pointer;border-radius:3px;font-size:11px;color:var(--text);transition:background .15s" onmouseover="this.style.background='rgba(91,138,247,.08)'" onmouseout="this.style.background=''">
        <input type="checkbox" ${checked} onchange="CategoryManager.toggle('${c.id}')" style="accent-color:var(--accent);width:13px;height:13px">
        ${escapeHtml(c.name)}
      </label>`;
    }).join('');
  },

  /**
   * Toggle category selection
   * @param {string} id - Category ID
   */
  toggle(id) {
    if (state.selectedCats.has(id)) state.selectedCats.delete(id);
    else state.selectedCats.add(id);
    this.renderCheckboxes();
    this.updateSummary();
  },

  /**
   * Toggle all categories
   * @param {boolean} select - Select all (true) or deselect all (false)
   */
  toggleAll(select) {
    state.selectedCats = select ? new Set(state.allCats.map((c) => c.id)) : new Set();
    this.renderCheckboxes();
    this.updateSummary();
  },

  /**
   * Toggle category panel visibility
   */
  togglePanel() {
    const panel = $('catPanel');
    panel.style.display = panel.style.display === 'none' ? '' : 'none';
  },

  /**
   * Update category summary display
   */
  updateSummary() {
    const total = state.allCats.length;
    const sel = state.selectedCats.size;
    $('catCountDisplay').textContent = sel === total ? `全部${total}个` : `${sel}/${total}`;

    const chips = state.allCats
      .filter((c) => state.selectedCats.has(c.id))
      .slice(0, 4)
      .map((c) => c.name)
      .join(', ');
    const extra = sel > 4 ? ` <span style="color:var(--text2)">+${sel - 4} 个更多</span>` : sel === 0 ? '<span style="color:var(--orange)">未选择</span>' : '';
    $('catChips').innerHTML = sel ? chips + extra : '<span style="color:var(--orange)">请选择品类</span>';

    // Update button text
    const btn = $('btnDiscover');
    if (btn && btn.style.display !== 'none') {
      btn.textContent = sel === total || !sel ? '开始挖掘' : `挖掘 ${sel} 个品类`;
    }
  },
};

// ═══════════════════════════════════════════════════════
// Schedule Management
// ═══════════════════════════════════════════════════════

const ScheduleManager = {
  /**
   * Load schedule configuration
   */
  async load() {
    try {
      const d = await API.getSchedule();
      const t = d.tasks?.['weekly-scan'];
      if (t) {
        state.scheduleEnabled = !!t.enabled;
        $('btnSchedule').style.color = state.scheduleEnabled ? 'var(--green)' : 'var(--text2)';
      }
    } catch (e) {
      // Silent fail
    }
  },

  /**
   * Toggle schedule panel visibility
   */
  async togglePanel() {
    const info = $('scheduleInfo');
    if (info.style.display !== 'block') {
      try {
        const d = await API.getSchedule();
        const t = d.tasks?.['weekly-scan'];
        if (t) {
          state.scheduleEnabled = !!t.enabled;
          $('btnSchedule').style.color = state.scheduleEnabled ? 'var(--green)' : 'var(--text2)';
          const last = d.last_runs?.['weekly-scan'];
          info.style.display = 'block';
          info.innerHTML = `<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            <span style="font-size:11px;color:var(--text2)">定时 <b>每周一 09:00</b> 自动扫描核心品类</span>
            <span style="font-size:11px;padding:2px 8px;border-radius:8px;background:${state.scheduleEnabled ? 'rgba(32,168,93,.12)' : 'rgba(107,113,133,.12)'};color:${state.scheduleEnabled ? 'var(--green)' : 'var(--text2)'}">${state.scheduleEnabled ? '已开启' : '已关闭'}</span>
            <label style="position:relative;display:inline-block;width:36px;height:18px;cursor:pointer">
              <input type="checkbox" ${state.scheduleEnabled ? 'checked' : ''} onchange="ScheduleManager.toggleEnable(this.checked)" style="opacity:0;width:0;height:0">
              <span style="position:absolute;inset:0;background:${state.scheduleEnabled ? 'var(--green)' : 'var(--surface3)'};border-radius:9px;transition:.3s"></span>
              <span style="position:absolute;height:14px;width:14px;left:2px;bottom:2px;background:white;border-radius:50%;transition:.3s;transform:${state.scheduleEnabled ? 'translateX(18px)' : ''}"></span>
            </label>
            ${last ? '<span style="font-size:10px;color:var(--text2)">上次执行: ' + new Date(last).toLocaleString() + '</span>' : ''}
          </div>`;
        } else {
          info.style.display = 'block';
          info.innerHTML = '<span style="font-size:11px;color:var(--text2)">未配置定时任务</span>';
        }
      } catch (e) {
        info.style.display = 'block';
        info.innerHTML = '<span style="font-size:11px;color:var(--red)">加载定时配置失败</span>';
      }
    } else {
      info.style.display = 'none';
    }
  },

  /**
   * Toggle schedule enabled state
   * @param {boolean} enabled - Enable or disable
   */
  async toggleEnable(enabled) {
    try {
      await API.toggleSchedule('weekly-scan', enabled);
      state.scheduleEnabled = enabled;
      $('btnSchedule').style.color = enabled ? 'var(--green)' : 'var(--text2)';
      await this.togglePanel();
    } catch (e) {
      $('actionInfo').textContent = '操作失败: ' + e.message;
    }
  },
};

// ═══════════════════════════════════════════════════════
// Scan Controller
// ═══════════════════════════════════════════════════════

const ScanController = {
  /**
   * Toggle category panel visibility
   */
  toggleCatPanel() {
    const panel = $('catPanel');
    panel.style.display = panel.style.display === 'none' ? '' : 'none';
  },

  /**
   * Update button visibility based on state
   */
  updateButtonVisibility() {
    const btnDiscover = $('btnDiscover');
    const btnStop = $('btnStop');
    const btnMatch = $('btnMatch');
    btnDiscover.style.display = 'none';
    btnStop.style.display = '';
    btnMatch.style.display = 'none';
    $('actionInfo').textContent = '';
  },

  /**
   * Reset buttons to ready state
   */
  resetButtons() {
    $('btnStop').style.display = 'none';
    $('btnDiscover').style.display = '';
    $('btnMatch').style.display = '';
    $('agentStatus').textContent = '就绪';
    $('agentStatus').className = 'status-badge ready';
  },
};

// ═══════════════════════════════════════════════════════
// Scan Workflow Functions
// ═══════════════════════════════════════════════════════

/**
 * Start discovery phase for selected categories
 */
async function runDiscover() {
  try {
    if (!state.allCats.length) {
      try {
        const d = await API.getCategories();
        state.allCats = d.categories || [];
      } catch (e) { }
      if (!state.allCats.length) {
        alert('品类列表未加载，请刷新后重试');
        return;
      }
    }

    // Use selected categories, or all if none selected
    const catsToScan = state.selectedCats.size
      ? state.allCats.filter((c) => state.selectedCats.has(c.id))
      : state.allCats;
    if (!catsToScan.length) {
      alert('请先选择要扫描的品类');
      return;
    }

    const btn = $('btnDiscover');
    const count = parseInt($('scanCount').value) || CONFIG.DEFAULT_SCAN_COUNT;

    ScanController.updateButtonVisibility();
    $('agentStatus').textContent = '工作中';
    $('agentStatus').className = 'status-badge busy';

    // Step 1: Fire POSTs for selected categories in parallel
    const catTasks = await Promise.all(
      catsToScan.map(async (cat, i) => {
        try {
          const p = new URLSearchParams({ category: cat.name, max_products: count });
          if (cat.bsr_url) p.append('bsr_url', cat.bsr_url);
          const d = await API.startDiscover(cat.name, count, cat.bsr_url);
          return { idx: i, cat: cat.name, taskId: d.task_id, error: false };
        } catch (e) {
          console.error(`Failed to start discover for ${cat.name}:`, e);
          return { idx: i, cat: cat.name, taskId: null, error: true };
        }
      })
    );

    const activeTasks = catTasks.filter((t) => !t.error);
    if (!activeTasks.length) {
      $('mainContent').innerHTML = '<div class="error-msg">所有品类均扫描失败</div>';
      btn.disabled = false;
      btn.textContent = '开始挖掘';
      ScanController.resetButtons();
      return;
    }

    // Step 2: Render robot grid
    state.allResults = [];
    state.allTaskIds = [];
    RobotGrid.render(catTasks);

    const robotStates = catTasks.map((t) => ({
      taskId: t.taskId,
      cat: t.cat,
      done: false,
      error: t.error,
      status: t.error ? '启动失败' : 'waiting',
      progress: 0,
      step: '',
      startTime: t.error ? null : Date.now(),
      elapsed: 0,
    }));

    // Step 3: Poll all tasks in parallel
    state.scanPollId = setInterval(async () => {
      let allDone = true;

      // Update elapsed time
      const now = Date.now();
      for (const rs of robotStates) {
        if (!rs.done && rs.startTime) rs.elapsed = Math.round((now - rs.startTime) / 1000);
      }

      // Poll each task
      for (let i = 0; i < robotStates.length; i++) {
        const rs = robotStates[i];
        if (rs.done) continue;
        if (rs.error) {
          rs.done = true;
          continue;
        }

        try {
          const d = await API.getTask(rs.taskId);
          rs.progress = Math.round((d.progress || 0) * 100);
          rs.step = d.current_step || '...';

          // Map phase to robot state
          if (d.phase === 'done' || (d.phase === 'review' && d.status === 'completed') || d.phase === 'matching') {
            rs.done = true;
            rs.status = 'complete';
            rs.progress = 100;
            const items = d.breakout_results || [];
            if (items && items.length) state.allResults.push(...items);
            state.allTaskIds.push(rs.taskId);
          } else if (d.phase === 'discover') {
            rs.status = 'scanning';
          } else {
            rs.status = 'analyzing';
          }
        } catch (e) {
          // Mark as error after threshold
          if (rs.startTime && Date.now() - rs.startTime > CONFIG.ERROR_THRESHOLD_MS) {
            rs.done = true;
            rs.status = 'error';
            rs.step = '连接失败';
            console.error(`Task ${rs.taskId} polling failed:`, e);
          }
        }

        if (!rs.done) allDone = false;
      }

      RobotGrid.update(robotStates);

      if (allDone) {
        clearInterval(state.scanPollId);
        state.scanPollId = null;
        finishScan();
      }
    }, CONFIG.POLL_INTERVAL_MS);
  } catch (error) {
    console.error('Discovery failed:', error);
    $('mainContent').innerHTML = `<div class="error-msg">扫描启动失败: ${escapeHtml(error.message)}</div>`;
    ScanController.resetButtons();
  }
}

/**
 * Finish scan workflow and display results
 * @param {boolean} [cancelled=false] - Whether scan was cancelled
 */
function finishScan(cancelled = false) {
  if (state.allResults.length) {
    renderCombinedResults(state.allResults);
    $('btnMatch').style.display = '';
    $('actionInfo').textContent = cancelled
      ? `⏹ 已停止，已获取 ${state.allResults.length} 个结果`
      : `✅ 并行扫描完成，共 ${state.allResults.length} 个选品机会`;
  } else {
    $('mainContent').innerHTML = `<div class="error-msg">${cancelled ? '扫描已停止' : '扫描完成'}，未发现符合条件的商品</div>`;
  }
  ScanController.resetButtons();
}

/**
 * Cancel all running scan tasks
 */
async function cancelScan() {
  if (!confirm('确定停止所有正在运行的扫描任务？')) return;
  $('btnStop').disabled = true;
  $('btnStop').textContent = '正在停止...';

  try {
    await API.cancelAll();
  } catch (e) {
    console.error('Cancel scan failed:', e);
  }

  if (state.scanPollId) {
    clearInterval(state.scanPollId);
    state.scanPollId = null;
  }
  finishScan(true);
}

/**
 * Start matching phase for all discovered tasks
 */
async function runMatch() {
  if (!state.allTaskIds.length) {
    alert('请先执行发现阶段');
    return;
  }

  const btn = $('btnMatch');
  btn.disabled = true;
  btn.textContent = '匹配全部品类中...';
  $('agentStatus').textContent = '工作中';
  $('agentStatus').className = 'status-badge busy';
  $('actionInfo').textContent = '';

  const total = state.allTaskIds.length;
  let matched = [];

  for (let i = 0; i < state.allTaskIds.length; i++) {
    const tid = state.allTaskIds[i];
    const catName = state.allCats[i] ? state.allCats[i].name : `品类 ${i + 1}`;

    $('mainContent').innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <div class="msg">🔗 ${escapeHtml(catName)} — 正在匹配 1688 (${i + 1}/${total})</div>
        <div style="margin-top:12px;width:300px;height:4px;background:var(--surface2);border-radius:2px;overflow:hidden;margin-left:auto;margin-right:auto">
          <div style="height:100%;background:var(--accent);border-radius:2px;transition:width .5s;width:${((i + 1) / total) * 100}%"></div>
        </div>
        <div class="sub">${Math.round(((i + 1) / total) * 100)}% · 品类 ${i + 1}/${total}</div>
      </div>`;

    try {
      await API.matchNow(tid);
      const taskData = await pollTask(tid);
      if (taskData && taskData.breakout_results) matched.push(...taskData.breakout_results);
    } catch (e) {
      console.warn(`Matching failed for task ${tid}:`, e);
    }
  }

  if (matched.length) {
    renderCombinedResults(matched);
  } else {
    $('mainContent').innerHTML = '<div class="error-msg">1688 匹配未返回结果</div>';
  }

  btn.disabled = false;
  btn.textContent = '🔗 匹配1688';
  ScanController.resetButtons();
}

/**
 * Poll a single task until completion
 * @param {string} tid - Task ID
 * @returns {Promise<object|null>} Task data or null
 */
async function pollTask(tid) {
  for (let i = 0; i < CONFIG.POLL_TASK_MAX_ITERATIONS; i++) {
    await new Promise((r) => setTimeout(r, CONFIG.POLL_TASK_INTERVAL_MS));
    try {
      const d = await API.getTask(tid);
      if (d.phase === 'done') return d;
    } catch (e) {
      // Silent retry
    }
  }
  try {
    return await API.getTask(tid);
  } catch (e) {
    return null;
  }
}

// ═══════════════════════════════════════════════════════
// Results Rendering
// ═══════════════════════════════════════════════════════

/**
 * Render combined results from multiple categories
 * @param {Array} results - Combined breakout results
 */
function renderCombinedResults(results) {
  renderResults({
    phase: 'done',
    breakout_results: results,
    category: `${state.allCats.length} 个品类`,
  });
}

/**
 * Main results renderer
 * @param {object} d - Task data with breakout_results
 */
async function renderResults(d) {
  const list = d.breakout_results || [];
  await ensureRules();

  if (!list.length) {
    $('mainContent').innerHTML = `<div class="empty-state"><div class="icon">📭</div><h2>暂无匹配结果</h2><p>未发现符合条件的商品，可调整选品规则后重试</p></div>`;
    return;
  }

  const sCount = list.filter((r) => r.breakout_score.grade === 'S级爆款').length;
  const aCount = list.filter((r) => r.breakout_score.grade === 'A级潜力').length;
  const bCount = list.filter((r) => r.breakout_score.grade === 'B级观察').length;
  const avgMarginList = list.filter((r) => r.profit_margin);
  const avgMargin = avgMarginList.length
    ? avgMarginList.reduce((s, r) => s + r.profit_margin, 0) / avgMarginList.length
    : 0;
  const riskWarns = list.filter((r) => r.risk_assessment && r.risk_assessment.level !== '低风险').length;
  const upTrends = list.filter((r) => r.trend_data && r.trend_data.direction === 'up').length;
  const matched = list.filter((r) => r.has_match).length;

  const parts = [];
  if (sCount) parts.push(`🎯 ${sCount} 个S级爆款`);
  if (aCount) parts.push(`💡 ${aCount} 个A级潜力`);
  if (avgMargin) parts.push(`💰 均利润率 ${formatNumber(avgMargin, 1)}%`);
  if (matched) parts.push(`🔗 ${matched}/${list.length} 已匹配1688`);
  if (upTrends) parts.push(`📈 ${upTrends} 个上升趋势`);
  if (riskWarns) parts.push(`⚠️ ${riskWarns} 个需关注风险`);

  $('mainContent').innerHTML = `
    <div class="summary-bar">
      <div class="summary-card s-grade"><div class="count">${sCount}</div><div class="label">S级爆款</div></div>
      <div class="summary-card a-grade"><div class="count">${aCount}</div><div class="label">A级潜力</div></div>
      <div class="summary-card info-grade"><div class="count">${bCount}</div><div class="label">B级观察</div></div>
      <div class="summary-card info-grade"><div class="count">${list.length}</div><div class="label">总计评估</div></div>
    </div>
    <div style="font-size:12px;color:var(--text2);margin-bottom:16px;line-height:1.8">
      🤖 <b>AI 分析：</b>${parts.join(' · ')}
      <span style="margin-left:8px;font-size:11px;opacity:.7">点击卡片展开详情 ›</span>
    </div>
    ${list.slice(0, CONFIG.MAX_RESULTS_DISPLAY).map((p, i) => ProductCard.render(p, i)).join('')}`;
}

/**
 * Toggle card expansion
 * @param {number} idx - Card index
 */
function toggleCard(idx) {
  const el = $(`expand-${idx}`);
  if (!el) return;
  el.classList.toggle('open');
  if (el.classList.contains('open')) {
    setTimeout(() => {
      const card = el.closest('.product-card');
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 100);
  }
}

// ═══════════════════════════════════════════════════════
// Rules Management
// ═══════════════════════════════════════════════════════

/**
 * Load and cache rules (lazy load)
 * @returns {Promise<object>} Rules object
 */
async function ensureRules() {
  if (state.rulesCache) return state.rulesCache;
  try {
    state.rulesCache = await API.getRules();
    return state.rulesCache;
  } catch (e) {
    return {};
  }
}

// ═══════════════════════════════════════════════════════
// Login Status
// ═══════════════════════════════════════════════════════

/**
 * Load 1688 login status
 */
async function loadLogin() {
  try {
    const d = await API.getLoginStatus();
    $('loginDot').textContent = d.status === 'ok' ? '1688' : d.status === 'needs_cookies' ? '需登录' : '不可用';
    $('loginDot').style.color = d.status === 'ok' ? 'var(--green)' : 'var(--red)';
  } catch (e) {
    // Silent fail
  }
}

// ═══════════════════════════════════════════════════════
// Global Error Handler
// ═══════════════════════════════════════════════════════

/**
 * Setup global error handlers
 */
function setupErrorHandler() {
  window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    const msg = event.reason?.message || '发生未知错误，请刷新页面重试';
    $('mainContent').innerHTML = `<div class="error-msg">${escapeHtml(msg)}</div>`;
    event.preventDefault();
  });

  window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    const msg = event.message || '页面发生错误';
    $('mainContent').innerHTML = `<div class="error-msg">${escapeHtml(msg)}</div>`;
  });
}

// ═══════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════

/**
 * Refresh all initial data
 */
async function refreshAll() {
  try {
    await Promise.all([loadLogin(), CategoryManager.load(), ScheduleManager.load()]);
  } catch (e) {
    console.error('Initialization error:', e);
  }
}

// Initialize on page load
setupErrorHandler();
refreshAll();
