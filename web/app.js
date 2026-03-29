const state = {
  data: null,
  marketplace: "all",
  query: "",
  selectedId: null,
  activeVariantId: null,
  authConfig: null,
  session: null,
  appliedPeriodStart: null,
  appliedPeriodEnd: null,
  draftPeriodStart: null,
  draftPeriodEnd: null,
};

const AUTO_REFRESH_MS = 60000;
const SESSION_STORAGE_KEY = "ecanalytics_session_token";
const MARKETPLACE_META = {
  amazon: { label: "Amazon", logo: "/amazon-logo.png" },
  rakuten: { label: "Rakuten", logo: "/rakuten-logo.png" },
};

const elements = {
  summaryStrip: document.getElementById("summaryStrip"),
  productList: document.getElementById("productList"),
  detailRoot: document.getElementById("detailRoot"),
  searchInput: document.getElementById("searchInput"),
  marketplaceFilters: document.getElementById("marketplaceFilters"),
  periodStart: document.getElementById("periodStart"),
  periodEnd: document.getElementById("periodEnd"),
  applyButton: document.getElementById("applyButton"),
  variantModal: document.getElementById("variantModal"),
  variantModalBackdrop: document.getElementById("variantModalBackdrop"),
  variantModalContent: document.getElementById("variantModalContent"),
  variantModalClose: document.getElementById("variantModalClose"),
  authOverlay: document.getElementById("authOverlay"),
  authMessage: document.getElementById("authMessage"),
  googleSignIn: document.getElementById("googleSignIn"),
  authStatus: document.getElementById("authStatus"),
  authEmail: document.getElementById("authEmail"),
  logoutButton: document.getElementById("logoutButton"),
};

let googleScriptPromise = null;
let dashboardAbortController = null;
let dashboardRequestId = 0;

function formatCurrency(value) {
  if (value == null) return "-";
  return new Intl.NumberFormat("ja-JP", {
    style: "currency",
    currency: "JPY",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatNumber(value) {
  if (value == null) return "-";
  return new Intl.NumberFormat("ja-JP", {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  }).format(value);
}

function parseDateValue(value) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateLabel(value) {
  const date = parseDateValue(value);
  if (!date) return "-";
  return new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function toIsoDate(year, month, day) {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function isoFromDate(date) {
  return toIsoDate(date.getFullYear(), date.getMonth() + 1, date.getDate());
}

function defaultPeriodRange(days = 30) {
  const end = new Date();
  const start = new Date(end.getTime() - (days - 1) * 24 * 60 * 60 * 1000);
  return {
    start: isoFromDate(start),
    end: isoFromDate(end),
  };
}

function extractDateRangeFromPath(path) {
  if (!path) return null;
  const compact = path.match(/(20\d{2})(\d{2})(\d{2})_(20\d{2})(\d{2})(\d{2})/);
  if (compact) {
    return {
      start: toIsoDate(compact[1], compact[2], compact[3]),
      end: toIsoDate(compact[4], compact[5], compact[6]),
    };
  }
  const loose = path.match(/(20\d{2})_(\d{1,2})_(\d{1,2})[～〜-](20\d{2})_(\d{1,2})_(\d{1,2})/);
  if (loose) {
    return {
      start: toIsoDate(loose[1], loose[2], loose[3]),
      end: toIsoDate(loose[4], loose[5], loose[6]),
    };
  }
  return null;
}

function deriveAvailableRange(data) {
  const sourceRanges = (data?.sources || [])
    .flatMap((source) => (source.paths?.length ? source.paths : source.path ? [source.path] : []))
    .map((path) => extractDateRangeFromPath(path))
    .filter(Boolean);
  const timelineDates = (data?.timeline || []).map((item) => item.date).filter(Boolean);
  const starts = [
    ...sourceRanges.map((range) => range.start),
    ...(timelineDates.length ? [timelineDates.slice().sort()[0]] : []),
  ].sort();
  const sortedTimelineDates = timelineDates.slice().sort();
  const ends = [
    ...sourceRanges.map((range) => range.end),
    ...(sortedTimelineDates.length ? [sortedTimelineDates[sortedTimelineDates.length - 1]] : []),
  ]
    .filter(Boolean)
    .sort();
  if (!starts.length || !ends.length) return null;
  return {
    start: starts[0],
    end: ends[ends.length - 1],
  };
}

function selectedRangeHasData() {
  return true;
}

function buildDashboardUrl() {
  const params = new URLSearchParams();
  if (state.appliedPeriodStart) params.set("start", state.appliedPeriodStart);
  if (state.appliedPeriodEnd) params.set("end", state.appliedPeriodEnd);
  const query = params.toString();
  return query ? `/api/dashboard?${query}` : "/api/dashboard";
}

function syncPeriodInputs() {
  elements.periodStart.value = state.draftPeriodStart || "";
  elements.periodEnd.value = state.draftPeriodEnd || "";
}

function setApplyButtonLoading(isLoading) {
  elements.applyButton.classList.toggle("is-loading", isLoading);
  elements.applyButton.setAttribute("aria-busy", isLoading ? "true" : "false");
  elements.applyButton.textContent = isLoading ? "反映中" : "反映";
}

function getSelectedDetail() {
  return state.data?.productDetails?.[state.selectedId] || null;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function isoDateRange(start, end) {
  if (!start || !end) return [];
  const dates = [];
  let cursor = parseDateValue(start);
  const limit = parseDateValue(end);
  if (!cursor || !limit) return dates;
  while (cursor <= limit) {
    dates.push(isoFromDate(cursor));
    cursor = new Date(cursor.getTime() + 24 * 60 * 60 * 1000);
  }
  return dates;
}

function buildVariantTimelineSeries(variant) {
  const source = new Map((variant?.timeline || []).map((item) => [item.date, item]));
  const firstDate = state.appliedPeriodStart || variant?.timeline?.[0]?.date;
  const lastDate = state.appliedPeriodEnd || variant?.timeline?.[variant.timeline.length - 1]?.date;
  const dates = isoDateRange(firstDate, lastDate);
  if (!dates.length) {
    return (variant?.timeline || []).map((item) => ({
      date: item.date,
      sales: item.sales || 0,
      units: item.units || 0,
    }));
  }
  return dates.map((date) => {
    const item = source.get(date);
    return {
      date,
      sales: item?.sales || 0,
      units: item?.units || 0,
    };
  });
}

function buildAggregateVariant(detail) {
  const timelineMap = new Map();
  let hasAnyTimeline = false;

  (detail?.variants || []).forEach((variant) => {
    if (!variant?.timelineAvailable || !variant.timeline?.length) {
      return;
    }
    hasAnyTimeline = true;
    variant.timeline.forEach((item) => {
      const current = timelineMap.get(item.date) || { sales: 0, units: 0 };
      current.sales += item.sales || 0;
      current.units += item.units || 0;
      timelineMap.set(item.date, current);
    });
  });

  return {
    id: "__aggregate_all__",
    label: "全SKU合計",
    sales: detail?.summary?.sales || 0,
    units: detail?.summary?.units || 0,
    timelineAvailable: hasAnyTimeline,
    timelineReason: hasAnyTimeline
      ? null
      : "この商品のSKU日別データが無いため、全SKU合計の推移は表示できません。",
    timeline: Array.from(timelineMap.entries())
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([date, values]) => ({
        date,
        sales: Math.round((values.sales || 0) * 100) / 100,
        units: Math.round((values.units || 0) * 100) / 100,
      })),
  };
}

function buildChartTicks(series) {
  if (!series.length) return [];
  if (series.length === 1) {
    return [
      {
        date: series[0].date,
        label: formatDateLabel(series[0].date),
        position: 50,
        edge: "single",
      },
    ];
  }

  const desiredTickCount = Math.min(series.length, 5);
  const indexes = new Set();
  for (let index = 0; index < desiredTickCount; index += 1) {
    indexes.add(Math.round(((series.length - 1) * index) / (desiredTickCount - 1)));
  }

  return Array.from(indexes)
    .sort((left, right) => left - right)
    .map((index) => ({
      date: series[index].date,
      label: formatDateLabel(series[index].date),
      position: (index / (series.length - 1)) * 100,
      edge: index === 0 ? "start" : index === series.length - 1 ? "end" : null,
    }));
}

function buildLineChart(series, key, stroke, formatter, label) {
  const width = Math.max(720, series.length * 42);
  const height = 190;
  const padding = { top: 16, right: 12, bottom: 22, left: 12 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const values = series.map((item) => item[key] || 0);
  const total = values.reduce((sum, value) => sum + value, 0);
  const maxValue = Math.max(...values, 1);
  const step = series.length > 1 ? plotWidth / (series.length - 1) : 0;
  const ticks = buildChartTicks(series);
  const points = series.map((item, index) => {
    const x = padding.left + step * index;
    const y = padding.top + plotHeight - ((item[key] || 0) / maxValue) * plotHeight;
    return [x, y];
  });
  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"}${point[0]},${point[1]}`).join(" ");
  const areaPath = `${linePath} L${padding.left + plotWidth},${padding.top + plotHeight} L${padding.left},${padding.top + plotHeight} Z`;
  const circles = points
    .filter((_, index) => series.length <= 14 || index === 0 || index === series.length - 1)
    .map((point) => `<circle cx="${point[0]}" cy="${point[1]}" r="3" fill="${stroke}"></circle>`)
    .join("");
  const guides = ticks
    .map((tick) => {
      const x = padding.left + (plotWidth * tick.position) / 100;
      return `<line x1="${x}" y1="${padding.top}" x2="${x}" y2="${padding.top + plotHeight}" stroke="rgba(27,39,57,0.07)" stroke-width="1"></line>`;
    })
    .join("");
  const axis = ticks
    .map((tick) => {
      const edgeClass = tick.edge ? ` is-${tick.edge}` : "";
      const positionStyle = tick.edge ? "" : `style="left:${tick.position}%;"`;
      return `<span class="variant-axis-tick${edgeClass}" ${positionStyle}>${escapeHtml(tick.label)}</span>`;
    })
    .join("");
  return `
    <section class="variant-chart-card">
      <div class="variant-chart-head">
        <span class="variant-chart-label">${label}</span>
        <strong class="variant-chart-value">${formatter(total)}</strong>
      </div>
      <svg class="variant-chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${label}">
        <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${padding.left + plotWidth}" y2="${padding.top + plotHeight}" stroke="rgba(27,39,57,0.12)" stroke-width="1"></line>
        ${guides}
        <text x="${padding.left + plotWidth}" y="${padding.top + 10}" text-anchor="end" fill="#6d7381" font-size="12">${escapeHtml(formatter(maxValue))}</text>
        <path d="${areaPath}" fill="${stroke}" opacity="0.14"></path>
        <path d="${linePath}" fill="none" stroke="${stroke}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
        ${circles}
      </svg>
      <div class="variant-chart-axis">${axis}</div>
    </section>
  `;
}

function closeVariantModal() {
  state.activeVariantId = null;
  elements.variantModal.classList.add("is-hidden");
  elements.variantModalContent.innerHTML = "";
}

function openVariantModal(variantId) {
  const detail = getSelectedDetail();
  const variant =
    variantId === "__aggregate_all__"
      ? buildAggregateVariant(detail)
      : detail?.variants?.find((item) => item.id === variantId);
  if (!detail || !variant) return;
  state.activeVariantId = variantId;
  const timeline = buildVariantTimelineSeries(variant);
  const hasTimeline = variant.timelineAvailable && timeline.length > 0;
  elements.variantModalContent.innerHTML = `
    <header class="variant-modal-header">
      <div class="variant-modal-kicker">${escapeHtml(detail.name)}</div>
      <h3 class="variant-modal-title">${escapeHtml(variant.label || "未設定")}</h3>
      <div class="variant-modal-meta">
        <span class="variant-modal-chip">売上 ${escapeHtml(formatCurrency(variant.sales))}</span>
        <span class="variant-modal-chip">個数 ${escapeHtml(formatNumber(variant.units))}</span>
        <span class="variant-modal-chip">${escapeHtml(
          state.appliedPeriodStart && state.appliedPeriodEnd
            ? `${formatDateLabel(state.appliedPeriodStart)} - ${formatDateLabel(state.appliedPeriodEnd)}`
            : "-"
        )}</span>
      </div>
    </header>
    ${
      hasTimeline
        ? `<div class="variant-chart-scroll">
            <div class="variant-chart-grid">
              ${buildLineChart(timeline, "units", "#b63b6a", formatNumber, "日別個数")}
              ${buildLineChart(timeline, "sales", "#7d2446", formatCurrency, "日別売上")}
            </div>
          </div>`
        : `<div class="variant-empty">${escapeHtml(variant.timelineReason || "このSKUの日別データはありません。")}</div>`
    }
  `;
  elements.variantModal.classList.remove("is-hidden");
}

function resolveColor(label) {
  const value = (label || "").toLowerCase();
  const palette = [
    { test: /ブラック|black|黒/, color: "#121212" },
    { test: /ホワイト|white|白|アイボリー/, color: "#fffdf7" },
    { test: /グレー|gray|grey|杢/, color: "#8b93a0" },
    { test: /ベージュ|beige|エクリュ|肌/, color: "#e0ba84" },
    { test: /モカ|moca|ブラウン|brown|茶|キャメル/, color: "#95623d" },
    { test: /ネイビー|navy/, color: "#234a8f" },
    { test: /ブルー|blue|青|アッシュブルー/, color: "#2f80ed" },
    { test: /グリーン|green|緑|カーキ|ペールグリーン/, color: "#1fa56b" },
    { test: /レッド|red|赤|ワイン|ボルドー/, color: "#d63a4c" },
    { test: /ピンク|pink/, color: "#ff5fa2" },
    { test: /パープル|purple|紫|ラベンダー/, color: "#8c5bff" },
    { test: /イエロー|yellow|黄|マスタード/, color: "#f4c430" },
    { test: /オレンジ|orange/, color: "#ff8a3d" },
  ];
  const matched = palette.find((entry) => entry.test.test(value));
  return matched?.color || "#c8a0ab";
}

function renderMarketplaceBadge(marketplace) {
  const meta = MARKETPLACE_META[marketplace];
  if (!meta) return "";
  return `
    <span class="market-badge ${marketplace}" aria-label="${meta.label}">
      <img class="market-logo" src="${meta.logo}" alt="${meta.label}" />
    </span>
  `;
}

function updateAuthStatus() {
  if (state.session?.email) {
    elements.authStatus.classList.remove("is-hidden");
    elements.authEmail.textContent = state.session.email;
  } else {
    elements.authStatus.classList.add("is-hidden");
    elements.authEmail.textContent = "";
  }
}

function setAuthMessage(message) {
  elements.authMessage.textContent = message;
}

function getStoredSessionToken() {
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY);
  } catch (error) {
    return null;
  }
}

function storeSessionToken(token) {
  try {
    if (token) {
      window.localStorage.setItem(SESSION_STORAGE_KEY, token);
    }
  } catch (error) {
    // no-op
  }
}

function clearSessionToken() {
  try {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch (error) {
    // no-op
  }
}

function withSessionHeaders(headers = {}) {
  const token = getStoredSessionToken();
  if (!token) {
    return headers;
  }
  return {
    ...headers,
    Authorization: `Bearer ${token}`,
  };
}

function showAuthOverlay(message) {
  if (message) setAuthMessage(message);
  elements.authOverlay.classList.remove("is-hidden");
}

function hideAuthOverlay() {
  elements.authOverlay.classList.add("is-hidden");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: withSessionHeaders(options.headers || {}),
  });
  let payload = null;
  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    const text = await response.text();
    payload = text ? { message: text } : {};
  }
  if (!response.ok) {
    const error = new Error(payload.error || payload.message || `HTTP ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function loadGoogleScript() {
  if (window.google?.accounts?.id) {
    return Promise.resolve();
  }
  if (googleScriptPromise) {
    return googleScriptPromise;
  }
  googleScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Google ログインの読み込みに失敗しました。"));
    document.head.appendChild(script);
  });
  return googleScriptPromise;
}

async function handleGoogleCredential(response) {
  setAuthMessage("認証中...");
  try {
    const authPayload = await fetchJson("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: response.credential }),
    });
    storeSessionToken(authPayload.sessionToken);
    const session = await fetchJson("/api/session", { cache: "no-store" });
    if (!session.authenticated) {
      throw new Error("ログイン情報を保存できませんでした。ブラウザの保存設定を確認してください。");
    }
    state.session = session;
    updateAuthStatus();
    hideAuthOverlay();
    await loadDashboard();
  } catch (error) {
    clearSessionToken();
    setAuthMessage(error.message);
  }
}

async function renderGoogleSignIn() {
  if (!state.authConfig?.googleClientId) {
    setAuthMessage("GOOGLE_CLIENT_ID が未設定です。");
    elements.googleSignIn.innerHTML = "";
    return;
  }
  await loadGoogleScript();
  elements.googleSignIn.innerHTML = "";
  window.google.accounts.id.initialize({
    client_id: state.authConfig.googleClientId,
    callback: handleGoogleCredential,
    ux_mode: "popup",
    auto_select: false,
    cancel_on_tap_outside: true,
  });
  window.google.accounts.id.renderButton(elements.googleSignIn, {
    theme: "outline",
    size: "large",
    shape: "pill",
    width: 280,
    text: "signin_with",
  });
}

async function ensureAuthenticated(message) {
  state.authConfig = await fetchJson("/api/auth/config");
  if (!state.authConfig.required) {
    hideAuthOverlay();
    return true;
  }

  try {
    const session = await fetchJson("/api/session");
    if (session.authenticated) {
      state.session = session;
      updateAuthStatus();
      hideAuthOverlay();
      return true;
    }
    clearSessionToken();
  } catch (error) {
    clearSessionToken();
  }

  state.session = null;
  updateAuthStatus();
  showAuthOverlay(message || `@${state.authConfig.allowedDomain} の Google アカウントでログインしてください。`);
  await renderGoogleSignIn();
  return false;
}

function buildHeatmap(detail) {
  const sizes = detail.sizeDistribution?.length
    ? detail.sizeDistribution.map((item) => item.label)
    : ["未設定"];
  const colors = detail.colorDistribution?.length
    ? detail.colorDistribution.map((item) => item.label)
    : ["未設定"];

  const matrix = new Map();
  const variantsByCell = new Map();
  detail.variants.forEach((variant) => {
    const size = variant.size || "未設定";
    const color = variant.color || "未設定";
    const key = `${size}__${color}`;
    const current = matrix.get(key) || { sales: 0, units: 0 };
    current.sales += variant.sales || 0;
    current.units += variant.units || 0;
    matrix.set(key, current);
    variantsByCell.set(key, variant);
  });

  const rowTotals = new Map();
  const columnTotals = new Map();
  let maxSales = 0;

  sizes.forEach((size) => {
    rowTotals.set(size, { sales: 0, units: 0 });
  });
  colors.forEach((color) => {
    columnTotals.set(color, { sales: 0, units: 0 });
  });

  detail.variants.forEach((variant) => {
    const size = variant.size || "未設定";
    const color = variant.color || "未設定";
    const row = rowTotals.get(size) || { sales: 0, units: 0 };
    row.sales += variant.sales || 0;
    row.units += variant.units || 0;
    rowTotals.set(size, row);
    const column = columnTotals.get(color) || { sales: 0, units: 0 };
    column.sales += variant.sales || 0;
    column.units += variant.units || 0;
    columnTotals.set(color, column);
  });

  matrix.forEach((value) => {
    maxSales = Math.max(maxSales, value.sales);
  });

  const headerCells = colors
    .map((color) => {
      const swatch = resolveColor(color);
      return `
        <th class="heatmap-column">
          <div class="heatmap-column-label">
            <span class="color-dot" style="background:${swatch}"></span>
            <span class="heatmap-column-text">${color}</span>
          </div>
        </th>
      `;
    })
    .join("");

  const rows = sizes
    .map((size) => {
      const cells = colors
        .map((color) => {
          const key = `${size}__${color}`;
          const value = matrix.get(key) || { sales: 0, units: 0 };
          const ratio = maxSales ? value.sales / maxSales : 0;
          const intensity = 0.08 + ratio * 0.92;
          const textColor = intensity >= 0.48 ? "#ffffff" : "#5f2940";
          const swatch = resolveColor(color);
          const variant = variantsByCell.get(key);
          const clickable = Boolean(variant);
          return `
            <td
              class="heatmap-cell ${clickable ? "is-clickable" : ""}"
              ${clickable ? `data-variant-id="${escapeHtml(variant.id)}"` : ""}
              style="background:rgba(214,58,106,${intensity.toFixed(3)}); --cell-color:${swatch}; --cell-text:${textColor};"
            >
              <div class="heatmap-sales">${formatCurrency(value.sales || 0)}</div>
              <div class="heatmap-units">${formatNumber(value.units || 0)}点</div>
            </td>
          `;
        })
        .join("");
      const rowTotal = rowTotals.get(size) || { sales: 0, units: 0 };
      return `
        <tr>
          <th class="heatmap-axis">${size}</th>
          ${cells}
          <td class="heatmap-total">
            <div class="heatmap-sales">${formatCurrency(rowTotal.sales)}</div>
            <div class="heatmap-units">${formatNumber(rowTotal.units)}点</div>
          </td>
        </tr>
      `;
    })
    .join("");

  const footerCells = colors
    .map((color) => {
      const total = columnTotals.get(color) || { sales: 0, units: 0 };
      return `
        <td class="heatmap-total">
          <div class="heatmap-sales">${formatCurrency(total.sales)}</div>
          <div class="heatmap-units">${formatNumber(total.units)}点</div>
        </td>
      `;
    })
    .join("");

  return `
    <div class="heatmap-wrap">
      <table class="heatmap-table">
        <thead>
          <tr>
            <th class="heatmap-corner">サイズ＼色</th>
            ${headerCells}
            <th class="heatmap-total-label">合計</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
        <tfoot>
          <tr>
            <th class="heatmap-axis">合計</th>
            ${footerCells}
            <td class="heatmap-total is-clickable" data-variant-id="__aggregate_all__">
              <div class="heatmap-sales">${formatCurrency(detail.summary.sales)}</div>
              <div class="heatmap-units">${formatNumber(detail.summary.units)}点</div>
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  `;
}

function getFilteredProducts() {
  if (!selectedRangeHasData()) return [];
  if (!state.data) return [];
  return state.data.products.filter((product) => {
    const marketplaceMatch = state.marketplace === "all" || product.marketplace === state.marketplace;
    const queryMatch = !state.query || product.name.toLowerCase().includes(state.query.toLowerCase());
    return marketplaceMatch && queryMatch;
  });
}

function renderSummary() {
  const products = getFilteredProducts();
  const totalSales = products.reduce((sum, product) => sum + product.sales, 0);
  const totalUnits = products.reduce((sum, product) => sum + product.units, 0);
  const periodLabel =
    state.appliedPeriodStart && state.appliedPeriodEnd
      ? `${formatDateLabel(state.appliedPeriodStart)} - ${formatDateLabel(state.appliedPeriodEnd)}`
      : "-";
  elements.summaryStrip.innerHTML = `
    <div class="summary-chip">商品数<strong>${formatNumber(products.length)}</strong></div>
    <div class="summary-chip">売上<strong>${formatCurrency(totalSales)}</strong></div>
    <div class="summary-chip">個数<strong>${formatNumber(totalUnits)}</strong></div>
    <div class="summary-chip">期間<strong>${periodLabel}</strong></div>
  `;
}

function renderProductList() {
  const products = getFilteredProducts();
  if (!products.length) {
    elements.productList.innerHTML = `<div class="empty-substate">該当商品なし</div>`;
    elements.detailRoot.innerHTML = `<div class="empty-state">商品を選択してください</div>`;
    return;
  }

  if (!products.some((product) => product.id === state.selectedId)) {
    state.selectedId = products[0].id;
  }

  elements.productList.innerHTML = products
    .map(
      (product) => `
        <article class="product-card ${product.id === state.selectedId ? "is-active" : ""}" data-product-id="${product.id}">
          <div class="product-card-top">
            <div class="product-name">${product.name}</div>
            ${renderMarketplaceBadge(product.marketplace)}
          </div>
          <div class="product-meta">
            <span>売上 ${formatCurrency(product.sales)}</span>
            <span>個数 ${formatNumber(product.units)}</span>
          </div>
        </article>
      `
    )
    .join("");

  elements.productList.querySelectorAll("[data-product-id]").forEach((card) => {
    card.addEventListener("click", () => {
      closeVariantModal();
      state.selectedId = card.dataset.productId;
      renderProductList();
      renderDetail();
    });
  });
}

function renderVariantTable(detail) {
  if (!detail.variants?.length) {
    return `<div class="empty-substate">バリエーションなし</div>`;
  }

  return `
    <div class="variant-table-wrap">
      <table class="variant-table">
        <thead>
          <tr>
            <th>色 / サイズ</th>
            <th>色</th>
            <th>サイズ</th>
            <th>売上</th>
            <th>個数</th>
          </tr>
        </thead>
        <tbody>
          ${detail.variants
            .map(
              (variant) => `
                <tr>
                  <td>${variant.label}</td>
                  <td>${variant.color || "-"}</td>
                  <td>${variant.size || "-"}</td>
                  <td>${formatCurrency(variant.sales)}</td>
                  <td>${formatNumber(variant.units)}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderDetail() {
  const detail = state.data?.productDetails?.[state.selectedId];
  if (!detail) {
    elements.detailRoot.innerHTML = `<div class="empty-state">商品を選択してください</div>`;
    return;
  }

  elements.detailRoot.innerHTML = `
    <div class="detail-header">
      <div class="detail-title-wrap">
        ${renderMarketplaceBadge(detail.marketplace)}
        <h2 class="detail-title">${detail.name}</h2>
      </div>
    </div>

    <div class="detail-body">
      <section class="metric-grid">
        <article class="metric-card">
          <span>売上</span>
          <strong>${formatCurrency(detail.summary.sales)}</strong>
        </article>
        <article class="metric-card">
          <span>個数</span>
          <strong>${formatNumber(detail.summary.units)}</strong>
        </article>
        <article class="metric-card">
          <span>バリエーション</span>
          <strong>${formatNumber(detail.summary.variantCount)}</strong>
        </article>
      </section>

      <section class="heatmap-card">
        <h3>サイズ × 色</h3>
        ${buildHeatmap(detail)}
      </section>

      <section class="variant-card">
        <h3>バリエーション別</h3>
        ${renderVariantTable(detail)}
      </section>
    </div>
  `;

  elements.detailRoot.querySelectorAll("[data-variant-id]").forEach((cell) => {
    cell.addEventListener("click", () => {
      openVariantModal(cell.dataset.variantId);
    });
  });
}

function render() {
  renderSummary();
  renderProductList();
  renderDetail();
}

async function loadDashboard() {
  if (state.authConfig?.required && !state.session) {
    return;
  }

  dashboardAbortController?.abort();
  dashboardAbortController = new AbortController();
  const requestId = ++dashboardRequestId;
  closeVariantModal();
  setApplyButtonLoading(true);
  try {
    const response = await fetch(buildDashboardUrl(), {
      cache: "no-store",
      credentials: "same-origin",
      headers: withSessionHeaders(),
      signal: dashboardAbortController.signal,
    });
    if (response.status === 401) {
      clearSessionToken();
      state.session = null;
      updateAuthStatus();
      await ensureAuthenticated("セッションの有効期限が切れました。もう一度ログインしてください。");
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    if (!state.appliedPeriodStart || !state.appliedPeriodEnd) {
      const fallbackRange = state.data?.period?.start && state.data?.period?.end
        ? { start: state.data.period.start, end: state.data.period.end }
        : defaultPeriodRange();
      state.appliedPeriodStart = fallbackRange.start;
      state.appliedPeriodEnd = fallbackRange.end;
      state.draftPeriodStart = fallbackRange.start;
      state.draftPeriodEnd = fallbackRange.end;
      syncPeriodInputs();
    }
    if (requestId !== dashboardRequestId) {
      return;
    }
    const products = getFilteredProducts();
    if (!products.some((product) => product.id === state.selectedId)) {
      state.selectedId = products[0]?.id ?? null;
    }
    render();
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    elements.detailRoot.innerHTML = `<div class="empty-state">${error.message}</div>`;
  } finally {
    if (requestId === dashboardRequestId) {
      setApplyButtonLoading(false);
      dashboardAbortController = null;
    }
  }
}

async function logout() {
  try {
    await fetchJson("/api/logout", { method: "POST" });
  } finally {
    clearSessionToken();
    state.session = null;
    updateAuthStatus();
    if (window.google?.accounts?.id) {
      window.google.accounts.id.disableAutoSelect();
    }
    showAuthOverlay(`@${state.authConfig?.allowedDomain || "andmellow.jp"} の Google アカウントでログインしてください。`);
    await renderGoogleSignIn();
  }
}

elements.searchInput.addEventListener("input", (event) => {
  state.query = event.target.value.trim();
  render();
});

function handlePeriodStartUpdate(value) {
  state.draftPeriodStart = value || null;
  if (state.draftPeriodStart && state.draftPeriodEnd && state.draftPeriodStart > state.draftPeriodEnd) {
    state.draftPeriodEnd = state.draftPeriodStart;
    elements.periodEnd.value = state.draftPeriodEnd;
  }
}

function handlePeriodEndUpdate(value) {
  state.draftPeriodEnd = value || null;
  if (state.draftPeriodStart && state.draftPeriodEnd && state.draftPeriodEnd < state.draftPeriodStart) {
    state.draftPeriodStart = state.draftPeriodEnd;
    elements.periodStart.value = state.draftPeriodStart;
  }
}

elements.periodStart.addEventListener("input", (event) => {
  handlePeriodStartUpdate(event.target.value);
});

elements.periodStart.addEventListener("change", (event) => {
  handlePeriodStartUpdate(event.target.value);
});

elements.periodEnd.addEventListener("input", (event) => {
  handlePeriodEndUpdate(event.target.value);
});

elements.periodEnd.addEventListener("change", (event) => {
  handlePeriodEndUpdate(event.target.value);
});

elements.applyButton.addEventListener("click", () => {
  handlePeriodStartUpdate(elements.periodStart.value);
  handlePeriodEndUpdate(elements.periodEnd.value);
  state.appliedPeriodStart = state.draftPeriodStart || null;
  state.appliedPeriodEnd = state.draftPeriodEnd || null;
  renderSummary();
  loadDashboard();
});

[elements.periodStart, elements.periodEnd].forEach((input) => {
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    state.appliedPeriodStart = state.draftPeriodStart || null;
    state.appliedPeriodEnd = state.draftPeriodEnd || null;
    loadDashboard();
  });
});

elements.marketplaceFilters.querySelectorAll("[data-marketplace]").forEach((button) => {
  button.addEventListener("click", () => {
    state.marketplace = button.dataset.marketplace;
    elements.marketplaceFilters.querySelectorAll("[data-marketplace]").forEach((candidate) => {
      candidate.classList.toggle("is-active", candidate === button);
    });
    render();
  });
});

elements.logoutButton.addEventListener("click", () => {
  logout();
});

elements.variantModalClose.addEventListener("click", () => {
  closeVariantModal();
});

elements.variantModalBackdrop.addEventListener("click", () => {
  closeVariantModal();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !elements.variantModal.classList.contains("is-hidden")) {
    closeVariantModal();
  }
});

async function bootstrap() {
  const range = defaultPeriodRange();
  state.appliedPeriodStart = range.start;
  state.appliedPeriodEnd = range.end;
  state.draftPeriodStart = range.start;
  state.draftPeriodEnd = range.end;
  syncPeriodInputs();
  const authenticated = await ensureAuthenticated();
  if (authenticated) {
    await loadDashboard();
  }
}

bootstrap();
window.setInterval(() => {
  if (state.session || !state.authConfig?.required) {
    loadDashboard();
  }
}, AUTO_REFRESH_MS);
