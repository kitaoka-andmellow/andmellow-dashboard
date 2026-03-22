const state = {
  data: null,
  marketplace: "all",
  query: "",
  selectedId: null,
  authConfig: null,
  session: null,
  availableRange: null,
  periodStart: null,
  periodEnd: null,
};

const AUTO_REFRESH_MS = 60000;

const elements = {
  summaryStrip: document.getElementById("summaryStrip"),
  productList: document.getElementById("productList"),
  detailRoot: document.getElementById("detailRoot"),
  refreshButton: document.getElementById("refreshButton"),
  searchInput: document.getElementById("searchInput"),
  marketplaceFilters: document.getElementById("marketplaceFilters"),
  periodStart: document.getElementById("periodStart"),
  periodEnd: document.getElementById("periodEnd"),
  authOverlay: document.getElementById("authOverlay"),
  authMessage: document.getElementById("authMessage"),
  googleSignIn: document.getElementById("googleSignIn"),
  authStatus: document.getElementById("authStatus"),
  authEmail: document.getElementById("authEmail"),
  logoutButton: document.getElementById("logoutButton"),
};

let googleScriptPromise = null;

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
  if (!data?.sources?.length) return null;
  const ranges = data.sources
    .flatMap((source) => (source.paths?.length ? source.paths : source.path ? [source.path] : []))
    .map((path) => extractDateRangeFromPath(path))
    .filter(Boolean);
  if (!ranges.length) return null;
  const starts = ranges.map((range) => range.start).sort();
  const ends = ranges.map((range) => range.end).sort();
  return {
    start: starts[0],
    end: ends[ends.length - 1],
  };
}

function selectedRangeHasData() {
  if (!state.availableRange || !state.periodStart || !state.periodEnd) return true;
  return !(state.periodEnd < state.availableRange.start || state.periodStart > state.availableRange.end);
}

function resolveColor(label) {
  const value = (label || "").toLowerCase();
  const palette = [
    { test: /ブラック|black|黒/, color: "#111111" },
    { test: /ホワイト|white|白|アイボリー/, color: "#f4f4f4" },
    { test: /グレー|gray|grey|杢/, color: "#8f8f8f" },
    { test: /ベージュ|beige|エクリュ|肌/, color: "#d8c2a1" },
    { test: /モカ|moca|ブラウン|brown|茶|キャメル/, color: "#8a6a52" },
    { test: /ネイビー|navy/, color: "#2a3b59" },
    { test: /ブルー|blue|青|アッシュブルー/, color: "#6d8eb8" },
    { test: /グリーン|green|緑|カーキ|ペールグリーン/, color: "#7a9b7e" },
    { test: /レッド|red|赤|ワイン|ボルドー/, color: "#b84a4a" },
    { test: /ピンク|pink/, color: "#d994a8" },
    { test: /パープル|purple|紫|ラベンダー/, color: "#9a89b8" },
    { test: /イエロー|yellow|黄|マスタード/, color: "#d8b44f" },
    { test: /オレンジ|orange/, color: "#d5884f" },
  ];
  const matched = palette.find((entry) => entry.test.test(value));
  return matched?.color || "#d7d7d7";
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
    await fetchJson("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: response.credential }),
    });
    const session = await fetchJson("/api/session", { cache: "no-store" });
    if (!session.authenticated) {
      throw new Error("ログイン情報を保存できませんでした。Cookie のブロック設定を確認してください。");
    }
    state.session = session;
    updateAuthStatus();
    hideAuthOverlay();
    await loadDashboard();
  } catch (error) {
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
  } catch (error) {
    // no-op
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
  detail.variants.forEach((variant) => {
    const size = variant.size || "未設定";
    const color = variant.color || "未設定";
    const key = `${size}__${color}`;
    const current = matrix.get(key) || { sales: 0, units: 0 };
    current.sales += variant.sales || 0;
    current.units += variant.units || 0;
    matrix.set(key, current);
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
          const intensity = maxSales ? 0.06 + (value.sales / maxSales) * 0.44 : 0.03;
          const swatch = resolveColor(color);
          return `
            <td class="heatmap-cell" style="background:rgba(0,0,0,${intensity.toFixed(3)}); --cell-color:${swatch};">
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
            <td class="heatmap-total">
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
    state.periodStart && state.periodEnd ? `${formatDateLabel(state.periodStart)} - ${formatDateLabel(state.periodEnd)}` : "-";
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
            <span class="market-badge ${product.marketplace}">${product.marketplace === "amazon" ? "Amazon" : "楽天"}</span>
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

  const marketLabel = detail.marketplace === "amazon" ? "Amazon" : "楽天";

  elements.detailRoot.innerHTML = `
    <div class="detail-header">
      <div class="detail-title-wrap">
        <span class="market-badge ${detail.marketplace}">${marketLabel}</span>
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

  elements.refreshButton.disabled = true;
  elements.refreshButton.textContent = "更新中";
  try {
    const response = await fetch("/api/dashboard", {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (response.status === 401) {
      state.session = null;
      updateAuthStatus();
      await ensureAuthenticated("セッションの有効期限が切れました。もう一度ログインしてください。");
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    state.availableRange = deriveAvailableRange(state.data);
    if (state.availableRange) {
      if (!state.periodStart) state.periodStart = state.availableRange.start;
      if (!state.periodEnd) state.periodEnd = state.availableRange.end;
      elements.periodStart.disabled = false;
      elements.periodEnd.disabled = false;
      elements.periodStart.min = state.availableRange.start;
      elements.periodStart.max = state.availableRange.end;
      elements.periodEnd.min = state.availableRange.start;
      elements.periodEnd.max = state.availableRange.end;
      elements.periodStart.value = state.periodStart;
      elements.periodEnd.value = state.periodEnd;
    } else {
      elements.periodStart.disabled = true;
      elements.periodEnd.disabled = true;
    }
    const products = getFilteredProducts();
    if (!products.some((product) => product.id === state.selectedId)) {
      state.selectedId = products[0]?.id ?? null;
    }
    render();
  } catch (error) {
    elements.detailRoot.innerHTML = `<div class="empty-state">${error.message}</div>`;
  } finally {
    elements.refreshButton.disabled = false;
    elements.refreshButton.textContent = "更新";
  }
}

async function logout() {
  try {
    await fetchJson("/api/logout", { method: "POST" });
  } finally {
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

elements.periodStart.addEventListener("input", (event) => {
  state.periodStart = event.target.value || state.availableRange?.start || null;
  if (state.periodEnd && state.periodStart && state.periodStart > state.periodEnd) {
    state.periodEnd = state.periodStart;
    elements.periodEnd.value = state.periodEnd;
  }
  render();
});

elements.periodEnd.addEventListener("input", (event) => {
  state.periodEnd = event.target.value || state.availableRange?.end || null;
  if (state.periodStart && state.periodEnd && state.periodEnd < state.periodStart) {
    state.periodStart = state.periodEnd;
    elements.periodStart.value = state.periodStart;
  }
  render();
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

elements.refreshButton.addEventListener("click", () => {
  loadDashboard();
});

elements.logoutButton.addEventListener("click", () => {
  logout();
});

async function bootstrap() {
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
