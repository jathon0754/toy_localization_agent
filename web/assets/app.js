const form = document.getElementById("run-form");
const countrySelect = document.getElementById("country");
const countryCustom = document.getElementById("country-custom");
const countryAddBtn = document.getElementById("country-add");
const targetLanguageSelect = document.getElementById("target-language");
const skipVisionInput = document.getElementById("skip-vision");
const allowIncompleteInput = document.getElementById("allow-incomplete");
const auto3dInput = document.getElementById("auto-3d");
const channelSelect = document.getElementById("channel");
const priceBandSelect = document.getElementById("price-band");
const materialConstraintsInput = document.getElementById("material-constraints");
const supplierConstraintsInput = document.getElementById("supplier-constraints");
const costCeilingInput = document.getElementById("cost-ceiling");
const runBtn = document.getElementById("run-btn");
const runBtnText = document.getElementById("run-btn-text");
const statusPill = document.getElementById("status-pill");

const logContainer = document.getElementById("log-container");
const runMetaContainer = document.getElementById("run-meta");
const cultureEl = document.getElementById("culture-output");
const regulationEl = document.getElementById("regulation-output");
const designEl = document.getElementById("design-output");
const planEl = document.getElementById("final-plan");
const warningsEl = document.getElementById("warnings-output");
const imageWrap = document.getElementById("image-wrap");
const showcaseWrap = document.getElementById("showcase-wrap");
const historyList = document.getElementById("history-list");
const historyRefreshBtn = document.getElementById("history-refresh");
const historyHint = document.getElementById("history-hint");

const cardCarousel = document.getElementById("result-cards");
const cardPrevBtn = document.getElementById("card-prev");
const cardNextBtn = document.getElementById("card-next");
const cardTabButtons = Array.from(document.querySelectorAll("[data-card-tab]"));
const resultCards = cardCarousel
  ? Array.from(cardCarousel.querySelectorAll("[data-card-id]"))
  : [];

const mockBtn = document.getElementById("mock-load");
const clearBtn = document.getElementById("clear-btn");

let activePollToken = 0;
let renderedLogs = [];
let currentImageUrl = "";
let currentShowcaseUrl = "";
let countriesLoadToken = 0;
let activeCardId = resultCards.length ? String(resultCards[0].dataset.cardId || "") : "";
let cardScrollRaf = 0;
let programmaticTargetCardId = "";
let programmaticTargetUntil = 0;
let historyLoadToken = 0;

const CUSTOM_MARKETS_STORAGE_KEY = "toy_localization.custom_markets";
const LAST_MARKET_STORAGE_KEY = "toy_localization.last_market";

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function asLines(value) {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  return String(value)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function pad2(num) {
  return String(num).padStart(2, "0");
}

function nowTimeTag() {
  const now = new Date();
  return `[${pad2(now.getHours())}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}]`;
}

function normalizeLogs(logs) {
  const lines = [];
  for (const entry of logs || []) {
    if (!entry) {
      continue;
    }
    for (const part of String(entry).split("\n")) {
      const trimmed = part.trim();
      if (!trimmed) {
        continue;
      }
      lines.push(trimmed);
    }
  }
  return lines;
}

function appendLogLine(message) {
  const line = document.createElement("div");
  line.className = "log-line";
  const time = document.createElement("span");
  time.className = "log-time";
  time.textContent = nowTimeTag();
  const msg = document.createElement("span");
  msg.textContent = message;
  line.appendChild(time);
  line.appendChild(msg);
  logContainer.appendChild(line);
}

function renderLogs(logs) {
  const lines = normalizeLogs(logs);
  const isPrefix =
    lines.length >= renderedLogs.length &&
    renderedLogs.every((line, index) => line === lines[index]);

  const shouldScroll =
    logContainer.scrollHeight - logContainer.scrollTop - logContainer.clientHeight < 80;

  if (!isPrefix) {
    logContainer.textContent = "";
    for (const line of lines) {
      appendLogLine(line);
    }
  } else {
    for (const line of lines.slice(renderedLogs.length)) {
      appendLogLine(line);
    }
  }

  renderedLogs = lines;
  if (shouldScroll) {
    logContainer.scrollTop = logContainer.scrollHeight;
  }

  if (!lines.length) {
    logContainer.textContent = "";
    appendLogLine("等待执行...");
    renderedLogs = ["等待执行..."];
  }
}

function formatSeconds(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return "";
  }
  if (num < 0.01) {
    return "<0.01s";
  }
  return `${num.toFixed(2)}s`;
}

function renderRunMeta(meta) {
  if (!runMetaContainer) {
    return;
  }
  const body = runMetaContainer.querySelector(".run-meta-body");
  if (!body) {
    return;
  }

  const runId = String((meta && meta.run_id) || "").trim();
  const outputDir = String((meta && meta.output_dir) || "").trim();
  const marketNormalized = String((meta && meta.market_normalized) || "").trim();
  const marketConfidence = String((meta && meta.market_confidence) || "").trim();
  const targetLanguage = String((meta && meta.target_language) || "").trim();
  const goToMarket = String((meta && meta.go_to_market) || "").trim();
  const priceBand = String((meta && meta.price_band) || "").trim();
  const materialConstraints = String((meta && meta.material_constraints) || "").trim();
  const supplierConstraints = String((meta && meta.supplier_constraints) || "").trim();
  const costCeiling = String((meta && meta.cost_ceiling) || "").trim();
  const marketNotes = Array.isArray(meta && meta.market_notes) ? meta.market_notes : [];
  const timings = meta && typeof meta.timings === "object" ? meta.timings : {};
  const knowledgeVersions = meta && typeof meta.knowledge_versions === "object" ? meta.knowledge_versions : {};
  const modelMeta = meta && typeof meta.model_meta === "object" ? meta.model_meta : {};

  if (!runId && !outputDir && !Object.keys(timings || {}).length) {
    body.textContent = "暂无运行信息";
    return;
  }

  const parts = [];
  if (runId) {
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">run_id</span><span class="run-meta-value">${escapeHtml(runId)}</span></div>`,
    );
  }
  if (outputDir) {
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">output_dir</span><span class="run-meta-value">${escapeHtml(outputDir)}</span></div>`,
    );
  }
  if (marketNormalized) {
    const label = marketConfidence ? `${marketNormalized} (${marketConfidence})` : marketNormalized;
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">market</span><span class="run-meta-value">${escapeHtml(label)}</span></div>`,
    );
  }
  if (targetLanguage) {
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">language</span><span class="run-meta-value">${escapeHtml(targetLanguage)}</span></div>`,
    );
  }
  if (goToMarket) {
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">go_to_market</span><span class="run-meta-value">${escapeHtml(goToMarket)}</span></div>`,
    );
  }
  if (priceBand) {
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">price_band</span><span class="run-meta-value">${escapeHtml(priceBand)}</span></div>`,
    );
  }
  if (costCeiling) {
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">cost_ceiling</span><span class="run-meta-value">${escapeHtml(costCeiling)}</span></div>`,
    );
  }
  if (materialConstraints) {
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">material_constraints</span><span class="run-meta-value">${escapeHtml(materialConstraints)}</span></div>`,
    );
  }
  if (supplierConstraints) {
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">supplier_constraints</span><span class="run-meta-value">${escapeHtml(supplierConstraints)}</span></div>`,
    );
  }
  if (marketNotes && marketNotes.length) {
    const notes = marketNotes.map((note) => escapeHtml(String(note))).join("；");
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">market notes</span><span class="run-meta-value">${notes}</span></div>`,
    );
  }

  if (knowledgeVersions && Object.keys(knowledgeVersions).length) {
    const items = Object.entries(knowledgeVersions)
      .filter(([, value]) => value)
      .map(([key, value]) => `${escapeHtml(key)}=${escapeHtml(String(value))}`)
      .join(" / ");
    if (items) {
      parts.push(
        `<div class="run-meta-row"><span class="run-meta-label">knowledge</span><span class="run-meta-value">${items}</span></div>`,
      );
    }
  }

  if (modelMeta && Object.keys(modelMeta).length) {
    const modelItems = [];
    if (modelMeta.llm_model) {
      modelItems.push(`llm=${escapeHtml(String(modelMeta.llm_model))}`);
    }
    if (modelMeta.embedding_model) {
      modelItems.push(`embed=${escapeHtml(String(modelMeta.embedding_model))}`);
    }
    if (modelMeta.image_gen_model) {
      modelItems.push(`image=${escapeHtml(String(modelMeta.image_gen_model))}`);
    }
    if (modelItems.length) {
      parts.push(
        `<div class="run-meta-row"><span class="run-meta-label">models</span><span class="run-meta-value">${modelItems.join(" / ")}</span></div>`,
      );
    }
  }

  const ordering = [
    "total",
    "culture",
    "regulation",
    "design",
    "coordinator",
    "prompt_refiner",
    "image_gen",
    "three_d_gen",
  ];
  const timingKeys = [];
  for (const key of ordering) {
    if (Object.prototype.hasOwnProperty.call(timings, key)) {
      timingKeys.push(key);
    }
  }
  for (const key of Object.keys(timings || {})) {
    if (!timingKeys.includes(key)) {
      timingKeys.push(key);
    }
  }

  if (timingKeys.length) {
    const chips = timingKeys
      .map((key) => {
        const label = `${key}:${formatSeconds(timings[key]) || "-"}`;
        return `<span class="run-meta-chip">${escapeHtml(label)}</span>`;
      })
      .join("");
    parts.push(
      `<div class="run-meta-row"><span class="run-meta-label">timings</span><span class="run-meta-timings">${chips}</span></div>`,
    );
  }

  body.innerHTML = parts.join("") || "暂无运行信息";
}

function bullets(value) {
  const lines = asLines(value);
  if (!lines.length) {
    return "";
  }
  return `<ul>${lines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>`;
}

function numbered(value) {
  const lines = asLines(value);
  if (!lines.length) {
    return "";
  }
  return `<ol>${lines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ol>`;
}

function text(value) {
  const t = String(value || "").trim();
  return t ? `<p>${escapeHtml(t)}</p>` : "";
}

function labelLine(label, value) {
  const t = String(value || "").trim();
  if (!t) {
    return "";
  }
  return `${label}: ${t}`;
}

function renderCulture(data, fallbackText) {
  if (data && typeof data === "object" && Object.keys(data).length > 0) {
    const parts = [];

    const add = (label, value) => {
      const lines = asLines(value);
      if (!lines.length) {
        const t = String(value || "").trim();
        if (!t) {
          return;
        }
        parts.push(`<p><span class="badge">${escapeHtml(label)}</span> ${escapeHtml(t)}</p>`);
        return;
      }
      parts.push(
        `<p><span class="badge">${escapeHtml(label)}</span> ${lines
          .map((line) => escapeHtml(line))
          .join("；")}</p>`,
      );
    };

    add("颜色", data.colors);
    add("符号", data.symbols);
    add("禁忌", data.taboos);
    add("沟通", data.communication_style);
    add("文案", data.packaging_copy_tone);
    add("备注", data.notes);

    cultureEl.innerHTML = parts.join("") || `<p>${escapeHtml(fallbackText || "暂无结果")}</p>`;
    return;
  }

  cultureEl.innerHTML = `<p>${escapeHtml(fallbackText || "暂无结果")}</p>`;
}

function renderRegulation(data, fallbackText) {
  if (data && typeof data === "object" && Object.keys(data).length > 0) {
    const parts = [];

    const section = (title, bodyHtml) => {
      if (!bodyHtml) {
        return;
      }
      parts.push(`<h4>${escapeHtml(title)}</h4>${bodyHtml}`);
    };

    section("要求", bullets(data.requirements));
    section("建议改造", bullets(data.design_changes));
    section("标签/文案", bullets(data.labeling));
    section("必测项", bullets(data.required_tests));
    section("年龄分级", text(data.age_grading));
    section("标签语言", text(data.label_language));
    section("材料/化学", bullets(data.materials_chemicals));
    section("备注", text(data.notes));

    regulationEl.innerHTML = parts.join("") || `<p>${escapeHtml(fallbackText || "暂无结果")}</p>`;
    return;
  }

  regulationEl.innerHTML = `<p>${escapeHtml(fallbackText || "暂无结果")}</p>`;
}

function renderDesign(data, fallbackText) {
  if (data && typeof data === "object" && Object.keys(data).length > 0) {
    const parts = [];

    const section = (title, bodyHtml) => {
      if (!bodyHtml) {
        return;
      }
      parts.push(`<h4>${escapeHtml(title)}</h4>${bodyHtml}`);
    };

    section("外观修改", bullets(data.appearance_changes));
    section("结构/安全", bullets(data.structure_safety_changes));
    section("材料", bullets(data.materials));
    section("成本影响", text(data.cost_impact));
    section("权衡", bullets(data.tradeoffs));
    section("备注", text(data.notes));

    designEl.innerHTML = parts.join("") || `<p>${escapeHtml(fallbackText || "暂无结果")}</p>`;
    return;
  }

  designEl.innerHTML = `<p>${escapeHtml(fallbackText || "暂无结果")}</p>`;
}

function renderFinalPlan(planData, fallbackText) {
  if (planData && typeof planData === "object" && Object.keys(planData).length > 0) {
    const parts = [];

    const section = (title, bodyHtml) => {
      if (!bodyHtml) {
        return;
      }
      parts.push(`<h4>${escapeHtml(title)}</h4>${bodyHtml}`);
    };

    section("概览", text(planData.summary));
    section("风险评分", text(planData.risk_score));
    section("合规阻塞", bullets(planData.compliance_blockers));
    section("必须动作", bullets(planData.must_actions));
    section("建议动作", bullets(planData.should_actions));
    section("可选动作", bullets(planData.could_actions));
    section("优先级动作", bullets(planData.priority_actions));
    section("文化动作", bullets(planData.cultural_actions));
    section("合规动作", bullets(planData.compliance_actions));
    section("设计变更", bullets(planData.design_changes));
    section("成本影响", text(planData.cost_impact));
    section("成本区间", text(planData.cost_estimate));
    section(
      "成本拆分",
      bullets([
        labelLine("模具/工装", planData.cost_tooling),
        labelLine("BOM/材料", planData.cost_bom),
        labelLine("测试认证", planData.cost_testing),
        labelLine("周期/排期", planData.cost_schedule),
      ]),
    );
    section("工期预估", text(planData.timeline_estimate));
    section("实施步骤", numbered(planData.implementation_steps));
    section("风险", bullets(planData.risks));
    section("需核实事项", bullets(planData.verification_required));
    section("待确认问题", bullets(planData.open_questions));
    section("假设", bullets(planData.assumptions));

    planEl.innerHTML = parts.join("") || `<p>${escapeHtml(fallbackText || "暂无结果")}</p>`;
    return;
  }

  planEl.innerHTML = `<p>${escapeHtml(fallbackText || "暂无结果")}</p>`;
}

function renderWarnings(payload) {
  if (!warningsEl) {
    return;
  }
  const data = payload && typeof payload === "object" ? payload : {};
  const complianceBlockers = data.compliance_blockers || [];
  const missingQuestions = data.missing_feature_questions || [];
  const stageWarnings = data.stage_warnings || {};
  const riskScore = data.risk_score || "";

  const parts = [];

  const section = (title, bodyHtml) => {
    if (!bodyHtml) {
      return;
    }
    parts.push(`<h4>${escapeHtml(title)}</h4>${bodyHtml}`);
  };

  section("风险评分", text(riskScore));
  section("合规阻塞", bullets(complianceBlockers));
  section("待补全信息", bullets(missingQuestions));

  const warningItems = Object.entries(stageWarnings)
    .filter(([, value]) => value)
    .map(([key, value]) => `${key}: ${value}`);
  section("系统警告", bullets(warningItems));

  warningsEl.innerHTML = parts.join("") || `<p>${escapeHtml("暂无风险/警告")}</p>`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function setStatus(kind, textValue) {
  statusPill.className = `badge status ${kind}`;
  statusPill.textContent = textValue;
}

function setStatusTransient(kind, textValue, durationMs = 1600) {
  const prevClass = statusPill.className;
  const prevText = statusPill.textContent;
  setStatus(kind, textValue);
  window.setTimeout(() => {
    if (statusPill.textContent !== textValue) {
      return;
    }
    statusPill.className = prevClass;
    statusPill.textContent = prevText;
  }, durationMs);
}

function setLoading(loading) {
  runBtn.disabled = loading;
  runBtnText.textContent = loading ? "运行中..." : "运行本地化";
}

function setActiveCard(cardId) {
  const id = String(cardId || "").trim();
  if (!id) {
    return;
  }
  activeCardId = id;
  for (const btn of cardTabButtons) {
    const isActive = String(btn.dataset.cardTab || "") === id;
    btn.classList.toggle("active", isActive);
  }
}

function scrollToCard(cardId, behavior = "smooth") {
  if (!cardCarousel) {
    return;
  }
  const id = String(cardId || "").trim();
  if (!id) {
    return;
  }
  const card = resultCards.find((el) => String(el.dataset.cardId || "") === id);
  if (!card) {
    return;
  }
  programmaticTargetCardId = id;
  programmaticTargetUntil = Date.now() + 2000;
  setActiveCard(id);
  card.scrollIntoView({ behavior, block: "nearest", inline: "start" });
  window.setTimeout(() => {
    if (!programmaticTargetCardId || programmaticTargetCardId !== id) {
      return;
    }
    if (activeCardId !== id) {
      card.scrollIntoView({ behavior: "auto", block: "nearest", inline: "start" });
      setActiveCard(id);
    }
  }, 320);
}

function cardIndex(cardId) {
  const id = String(cardId || "").trim();
  if (!id) {
    return -1;
  }
  return resultCards.findIndex((el) => String(el.dataset.cardId || "") === id);
}

function moveCard(delta) {
  if (!resultCards.length) {
    return;
  }
  const idx = cardIndex(activeCardId);
  const next = idx < 0 ? 0 : (idx + delta + resultCards.length) % resultCards.length;
  const nextId = String(resultCards[next].dataset.cardId || "");
  scrollToCard(nextId);
}

function updateActiveCardFromScroll() {
  if (!cardCarousel || !resultCards.length) {
    return;
  }

  const carouselRect = cardCarousel.getBoundingClientRect();
  const center = carouselRect.left + carouselRect.width / 2;
  let bestId = activeCardId;
  let bestDistance = Number.POSITIVE_INFINITY;

  for (const card of resultCards) {
    const id = String(card.dataset.cardId || "");
    if (!id) {
      continue;
    }
    const cardRect = card.getBoundingClientRect();
    const cardCenter = cardRect.left + cardRect.width / 2;
    const dist = Math.abs(cardCenter - center);
    if (dist < bestDistance) {
      bestDistance = dist;
      bestId = id;
    }
  }

  const now = Date.now();
  if (programmaticTargetCardId) {
    if (bestId === programmaticTargetCardId) {
      programmaticTargetCardId = "";
      programmaticTargetUntil = 0;
      setActiveCard(bestId);
      return;
    }
    if (now < programmaticTargetUntil) {
      setActiveCard(programmaticTargetCardId);
      return;
    }
    programmaticTargetCardId = "";
    programmaticTargetUntil = 0;
  }

  if (bestId && bestId !== activeCardId) {
    setActiveCard(bestId);
  }
}

function resetMedia() {
  imageWrap.className = "media-placeholder";
  imageWrap.innerHTML = '<div><i class="fa-solid fa-image"></i></div><div>暂无概念图</div>';
  showcaseWrap.className = "media-placeholder";
  showcaseWrap.innerHTML = '<div><i class="fa-solid fa-cube"></i></div><div>暂无展示结果</div>';
}

function renderImage(url) {
  if (!url || url === currentImageUrl) {
    return;
  }
  currentImageUrl = url;
  const img = document.createElement("img");
  img.src = url;
  img.alt = "concept";
  imageWrap.className = "media-placeholder";
  imageWrap.textContent = "";
  imageWrap.appendChild(img);
}

function renderShowcase(url) {
  if (!url || url === currentShowcaseUrl) {
    return;
  }
  currentShowcaseUrl = url;

  showcaseWrap.className = "media-placeholder";
  showcaseWrap.textContent = "";

  if (url.toLowerCase().endsWith(".mp4")) {
    const video = document.createElement("video");
    video.src = url;
    video.controls = true;
    video.loop = true;
    showcaseWrap.appendChild(video);
    return;
  }

  const img = document.createElement("img");
  img.src = url;
  img.alt = "showcase";
  showcaseWrap.appendChild(img);
}

function resetOutputs() {
  cultureEl.textContent = "暂无结果";
  regulationEl.textContent = "暂无结果";
  designEl.textContent = "暂无结果";
  planEl.textContent = "暂无结果";
  if (warningsEl) {
    warningsEl.textContent = "暂无风险/警告";
  }
  renderedLogs = [];
  currentImageUrl = "";
  currentShowcaseUrl = "";
  renderLogs([]);
  renderRunMeta({});
  resetMedia();
  scrollToCard("logs", "auto");
}

function hasText(value) {
  return String(value || "").trim().length > 0;
}

function hasObject(value) {
  return value && typeof value === "object" && Object.keys(value).length > 0;
}

function truncateText(value, maxLen = 120) {
  const text = String(value || "").trim();
  if (text.length <= maxLen) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLen - 1))}…`;
}

function formatTimestamp(ts) {
  const num = Number(ts);
  if (!Number.isFinite(num) || num <= 0) {
    return "";
  }
  const date = new Date(num * 1000);
  const y = date.getFullYear();
  const m = pad2(date.getMonth() + 1);
  const d = pad2(date.getDate());
  const hh = pad2(date.getHours());
  const mm = pad2(date.getMinutes());
  return `${y}-${m}-${d} ${hh}:${mm}`;
}

function readCustomMarkets() {
  try {
    const raw = localStorage.getItem(CUSTOM_MARKETS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.map((item) => String(item).trim()).filter(Boolean);
  } catch (error) {
    return [];
  }
}

function writeCustomMarkets(markets) {
  try {
    localStorage.setItem(CUSTOM_MARKETS_STORAGE_KEY, JSON.stringify(markets));
  } catch (error) {
    // best-effort
  }
}

function readLastMarket() {
  try {
    return String(localStorage.getItem(LAST_MARKET_STORAGE_KEY) || "").trim();
  } catch (error) {
    return "";
  }
}

function writeLastMarket(value) {
  try {
    localStorage.setItem(LAST_MARKET_STORAGE_KEY, String(value || "").trim());
  } catch (error) {
    // best-effort
  }
}

function isUnsafeMarket(value) {
  const raw = String(value || "");
  return (
    raw.includes("/") ||
    raw.includes("\\") ||
    raw.includes("..") ||
    raw.includes(":") ||
    raw.includes("\u0000")
  );
}

function rememberMarket(marketValue) {
  const trimmed = String(marketValue || "").trim();
  if (!trimmed || isUnsafeMarket(trimmed)) {
    return;
  }
  const custom = readCustomMarkets();
  const exists = custom.some((item) => item.toLowerCase() === trimmed.toLowerCase());
  if (!exists) {
    custom.push(trimmed);
    writeCustomMarkets(custom);
  }
}

function addMarketOption(marketValue) {
  const trimmed = String(marketValue || "").trim();
  if (!trimmed) {
    setStatusTransient("error", "请输入国家/地区");
    return;
  }
  if (isUnsafeMarket(trimmed)) {
    setStatusTransient("error", "国家/地区格式不支持（避免 / \\ .. :）");
    return;
  }

  const custom = readCustomMarkets();
  const exists = custom.some((item) => item.toLowerCase() === trimmed.toLowerCase());
  if (!exists) {
    custom.push(trimmed);
    writeCustomMarkets(custom);
  }

  writeLastMarket(trimmed);
  loadCountries(trimmed);
  countryCustom.value = "";
  setStatusTransient("done", "已添加");
}

function historyStatusKind(status) {
  const raw = String(status || "").toLowerCase();
  if (raw === "done") {
    return "done";
  }
  if (raw === "blocked") {
    return "blocked";
  }
  if (raw === "error") {
    return "error";
  }
  if (raw === "queued" || raw === "running") {
    return "running";
  }
  return "idle";
}

function historyStatusLabel(status) {
  const raw = String(status || "").toLowerCase();
  if (raw === "done") {
    return "完成";
  }
  if (raw === "blocked") {
    return "需补全";
  }
  if (raw === "error") {
    return "失败";
  }
  if (raw === "queued") {
    return "排队中";
  }
  if (raw === "running") {
    return "运行中";
  }
  return raw || "未知";
}

function applyHistoryJob(jobEntry) {
  const job = jobEntry && typeof jobEntry === "object" ? jobEntry : {};
  const payload = job.payload && typeof job.payload === "object" ? job.payload : {};
  const result = job.result && typeof job.result === "object" ? job.result : {};

  const logs = job.logs || result.logs || [];
  renderLogs(logs);
  renderRunMeta({
    run_id: result.run_id || job.job_id || "",
    output_dir: result.output_dir || "",
    market_normalized: result.market_normalized || payload.country || "",
    market_confidence: result.market_confidence || "",
    market_notes: result.market_notes || [],
    target_language: result.target_language || "",
    go_to_market: result.go_to_market || payload.go_to_market || "",
    price_band: result.price_band || payload.price_band || "",
    material_constraints: result.material_constraints || payload.material_constraints || "",
    supplier_constraints: result.supplier_constraints || payload.supplier_constraints || "",
    cost_ceiling: result.cost_ceiling || payload.cost_ceiling || "",
    knowledge_versions: result.knowledge_versions || {},
    model_meta: result.model_meta || {},
    timings: result.timings || {},
  });

  if (hasObject(result.culture_data) || hasText(result.culture_suggestion)) {
    renderCulture(result.culture_data, result.culture_suggestion);
  }
  if (hasObject(result.regulation_data) || hasText(result.regulation_suggestion)) {
    renderRegulation(result.regulation_data, result.regulation_suggestion);
  }
  if (hasObject(result.design_data) || hasText(result.design_suggestion)) {
    renderDesign(result.design_data, result.design_suggestion);
  }
  if (hasObject(result.final_plan_data) || hasText(result.final_plan)) {
    renderFinalPlan(result.final_plan_data, result.final_plan);
  }
  renderWarnings({
    compliance_blockers: result.compliance_blockers || [],
    missing_feature_questions: result.missing_feature_questions || [],
    stage_warnings: result.stage_warnings || {},
    risk_score: result.risk_score || (result.final_plan_data && result.final_plan_data.risk_score) || "",
  });
  if (hasText(result.image_url)) {
    renderImage(result.image_url);
  }
  if (hasText(result.showcase_url)) {
    renderShowcase(result.showcase_url);
  }

  const market = String(payload.country || "").trim();
  const description = String(payload.description || "").trim();
  if (description) {
    document.getElementById("description").value = description;
  }
  if (market && !isUnsafeMarket(market)) {
    rememberMarket(market);
    writeLastMarket(market);
    loadCountries(market);
  }

  if (targetLanguageSelect) {
    const langValue = String(payload.target_language || "").trim();
    targetLanguageSelect.value = langValue;
  }

  if ("skip_vision" in payload) {
    skipVisionInput.checked = Boolean(payload.skip_vision);
  }
  if ("allow_incomplete" in payload && allowIncompleteInput) {
    allowIncompleteInput.checked = Boolean(payload.allow_incomplete);
  }
  if ("auto_3d" in payload) {
    auto3dInput.checked = Boolean(payload.auto_3d);
  }
  if (channelSelect) {
    channelSelect.value = String(payload.go_to_market || "").trim();
  }
  if (priceBandSelect) {
    priceBandSelect.value = String(payload.price_band || "").trim();
  }
  if (materialConstraintsInput) {
    materialConstraintsInput.value = String(payload.material_constraints || "");
  }
  if (supplierConstraintsInput) {
    supplierConstraintsInput.value = String(payload.supplier_constraints || "");
  }
  if (costCeilingInput) {
    costCeilingInput.value = String(payload.cost_ceiling || "");
  }
  syncVisionFlags();
}

async function loadHistory(jobId) {
  const id = String(jobId || "").trim();
  if (!id) {
    return;
  }

  activePollToken += 1;
  setLoading(false);

  try {
    const resp = await fetch(`/api/history/${encodeURIComponent(id)}`);
    const data = await resp.json();
    if (!resp.ok || !data || !data.success) {
      throw new Error((data && (data.error || data.detail)) || `HTTP ${resp.status}`);
    }

    applyHistoryJob(data.job);
    const kind = historyStatusKind(data.job && data.job.status);
    setStatus(kind, historyStatusLabel(data.job && data.job.status));
    scrollToCard("plan");
  } catch (error) {
    setStatus("error", "加载失败");
    planEl.textContent = String(error);
  }
}

function renderHistory(items) {
  if (!historyList) {
    return;
  }
  const list = Array.isArray(items) ? items : [];
  historyList.textContent = "";

  if (!list.length) {
    const empty = document.createElement("div");
    empty.className = "media-placeholder";
    empty.textContent = "暂无历史，先运行一次即可生成。";
    historyList.appendChild(empty);
    if (historyHint) {
      historyHint.style.display = "none";
    }
    return;
  }

  if (historyHint) {
    historyHint.style.display = "";
  }

  for (const item of list) {
    const jobId = String((item && item.job_id) || "").trim();
    if (!jobId) {
      continue;
    }

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "history-item";

    const market = String((item && item.country) || "").trim() || "(未命名市场)";
    const createdAt = formatTimestamp(item && item.created_at);
    const desc = truncateText(item && item.description, 120);
    const status = String((item && item.status) || "").trim();
    const kind = historyStatusKind(status);
    const label = historyStatusLabel(status);
    const flags = [];
    if (item && item.skip_vision) {
      flags.push("仅文本");
    }
    if (item && item.auto_3d) {
      flags.push("3D");
    }
    if (item && item.allow_incomplete) {
      flags.push("允许缺失");
    }

    const goToMarket = String((item && item.go_to_market) || "").trim();
    const priceBand = String((item && item.price_band) || "").trim();
    if (goToMarket) {
      flags.push(`渠道:${goToMarket}`);
    }
    if (priceBand) {
      flags.push(`价位:${priceBand}`);
    }

    const meta = [createdAt, ...flags].filter(Boolean).join(" · ");
    const errorText = kind === "error" ? truncateText(item && item.error, 120) : "";

    btn.innerHTML = `
      <div class="history-top">
        <div>
          <div class="history-title">${escapeHtml(market)}</div>
          <div class="history-meta">${escapeHtml(meta)}</div>
        </div>
        <span class="badge status ${escapeHtml(kind)}">${escapeHtml(label)}</span>
      </div>
      ${desc ? `<div class="history-desc">${escapeHtml(desc)}</div>` : ""}
      ${errorText ? `<div class="history-desc">错误：${escapeHtml(errorText)}</div>` : ""}
    `;

    btn.addEventListener("click", () => loadHistory(jobId));
    historyList.appendChild(btn);
  }
}

async function refreshHistory() {
  if (!historyList) {
    return;
  }
  const token = (historyLoadToken += 1);
  historyList.innerHTML = '<div class="media-placeholder">加载中...</div>';

  try {
    const resp = await fetch("/api/history?limit=60");
    const data = await resp.json();
    if (token !== historyLoadToken) {
      return;
    }

    if (!resp.ok || !data || !data.success) {
      throw new Error((data && (data.error || data.detail)) || `HTTP ${resp.status}`);
    }
    renderHistory(data.items || []);
  } catch (error) {
    if (token !== historyLoadToken) {
      return;
    }
    historyList.innerHTML = `<div class="media-placeholder">加载失败：${escapeHtml(String(error))}</div>`;
    if (historyHint) {
      historyHint.style.display = "none";
    }
  }
}

function syncVisionFlags() {
  if (skipVisionInput.checked) {
    auto3dInput.checked = false;
    auto3dInput.disabled = true;
  } else {
    auto3dInput.disabled = false;
  }
}

async function loadCountries(desiredSelection = "") {
  const token = (countriesLoadToken += 1);
  const fallback = ["japan", "usa", "germany", "brazil", "china"];
  const customMarkets = readCustomMarkets();
  const lastMarket = desiredSelection || readLastMarket();
  try {
    const response = await fetch("/api/countries");
    const data = await response.json();
    const countries = data.countries || fallback;

    if (token !== countriesLoadToken) {
      return;
    }

    countrySelect.innerHTML = "";

    const normalized = new Set();
    const merged = [];
    for (const country of countries) {
      const trimmed = String(country || "").trim();
      if (!trimmed) {
        continue;
      }
      const key = trimmed.toLowerCase();
      if (normalized.has(key)) {
        continue;
      }
      normalized.add(key);
      merged.push(trimmed);
    }
    for (const market of customMarkets) {
      const trimmed = String(market || "").trim();
      if (!trimmed) {
        continue;
      }
      const key = trimmed.toLowerCase();
      if (normalized.has(key)) {
        continue;
      }
      normalized.add(key);
      merged.push(trimmed);
    }

    for (const country of merged) {
      const option = document.createElement("option");
      option.value = country;
      option.textContent = country;
      countrySelect.appendChild(option);
    }

    if (lastMarket) {
      const match = Array.from(countrySelect.options).find(
        (option) => String(option.value || "").toLowerCase() === lastMarket.toLowerCase(),
      );
      if (match) {
        countrySelect.value = match.value;
      }
    }
  } catch (error) {
    if (token !== countriesLoadToken) {
      return;
    }
    countrySelect.innerHTML = "";

    const normalized = new Set();
    const merged = [];
    for (const country of fallback) {
      const trimmed = String(country || "").trim();
      if (!trimmed) {
        continue;
      }
      const key = trimmed.toLowerCase();
      if (normalized.has(key)) {
        continue;
      }
      normalized.add(key);
      merged.push(trimmed);
    }
    for (const market of customMarkets) {
      const trimmed = String(market || "").trim();
      if (!trimmed) {
        continue;
      }
      const key = trimmed.toLowerCase();
      if (normalized.has(key)) {
        continue;
      }
      normalized.add(key);
      merged.push(trimmed);
    }

    for (const country of merged) {
      const option = document.createElement("option");
      option.value = country;
      option.textContent = country;
      countrySelect.appendChild(option);
    }

    if (lastMarket) {
      const match = Array.from(countrySelect.options).find(
        (option) => String(option.value || "").toLowerCase() === lastMarket.toLowerCase(),
      );
      if (match) {
        countrySelect.value = match.value;
      }
    }
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  activePollToken += 1;
  const pollToken = activePollToken;

  const countryInput = countryCustom.value.trim() || countrySelect.value.trim();
  const description = document.getElementById("description").value.trim();

  if (!countryInput) {
    setStatus("error", "请填写国家码");
    return;
  }
  if (!description) {
    setStatus("error", "请填写玩具描述");
    return;
  }

  if (isUnsafeMarket(countryInput)) {
    setStatus("error", "国家/地区格式不支持（避免 / \\ .. :）");
    return;
  }

  writeLastMarket(countryInput);
  setLoading(true);
  setStatus("running", "排队中");
  resetOutputs();
  scrollToCard("logs", "auto");
  appendLogLine(`提交任务：country=${countryInput}, skip_vision=${skipVisionInput.checked}, auto_3d=${auto3dInput.checked}`);

  try {
    const response = await fetch("/api/run_async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        country: countryInput,
        description,
        skip_vision: skipVisionInput.checked,
        auto_3d: auto3dInput.checked,
        target_language: targetLanguageSelect ? targetLanguageSelect.value.trim() : "",
        allow_incomplete: allowIncompleteInput ? allowIncompleteInput.checked : false,
        go_to_market: channelSelect ? channelSelect.value.trim() : "",
        price_band: priceBandSelect ? priceBandSelect.value.trim() : "",
        material_constraints: materialConstraintsInput ? materialConstraintsInput.value.trim() : "",
        supplier_constraints: supplierConstraintsInput ? supplierConstraintsInput.value.trim() : "",
        cost_ceiling: costCeilingInput ? costCeilingInput.value.trim() : "",
      }),
    });

    let data = null;
    try {
      data = await response.json();
    } catch (error) {
      data = null;
    }

    if (!response.ok) {
      setStatus("error", "运行失败");
      const detail = data && data.detail ? JSON.stringify(data.detail) : "";
      planEl.textContent = detail || (data && data.error) || `HTTP ${response.status}`;
      appendLogLine(detail || JSON.stringify(data) || "请求失败，请检查服务日志。");
      return;
    }

    if (!data.success) {
      setStatus("error", "运行失败");
      planEl.textContent = data.error || "未知错误";
      renderLogs(data.logs || []);
      return;
    }

    const jobId = data.job_id;
    if (!jobId) {
      setStatus("error", "运行失败");
      planEl.textContent = "未返回 job_id";
      return;
    }
    renderRunMeta({ run_id: jobId });

    while (pollToken === activePollToken) {
      const jobResp = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
      if (!jobResp.ok) {
        setStatus("error", "运行失败");
        const responseText = await jobResp.text();
        planEl.textContent = responseText || `查询任务失败: HTTP ${jobResp.status}`;
        break;
      }

      const job = await jobResp.json();
      renderLogs(job.logs || []);
      renderRunMeta({
        run_id: job.run_id || job.job_id || "",
        output_dir: job.output_dir || "",
        market_normalized: job.market_normalized || "",
        market_confidence: job.market_confidence || "",
        market_notes: job.market_notes || [],
        target_language: job.target_language || "",
        go_to_market: job.go_to_market || "",
        price_band: job.price_band || "",
        material_constraints: job.material_constraints || "",
        supplier_constraints: job.supplier_constraints || "",
        cost_ceiling: job.cost_ceiling || "",
        knowledge_versions: job.knowledge_versions || {},
        model_meta: job.model_meta || {},
        timings: job.timings || {},
      });

      if (hasObject(job.culture_data) || hasText(job.culture_suggestion)) {
        renderCulture(job.culture_data, job.culture_suggestion);
      }
      if (hasObject(job.regulation_data) || hasText(job.regulation_suggestion)) {
        renderRegulation(job.regulation_data, job.regulation_suggestion);
      }
      if (hasObject(job.design_data) || hasText(job.design_suggestion)) {
        renderDesign(job.design_data, job.design_suggestion);
      }
      if (hasObject(job.final_plan_data) || hasText(job.final_plan)) {
        renderFinalPlan(job.final_plan_data, job.final_plan);
      }
      renderWarnings({
        compliance_blockers: job.compliance_blockers || [],
        missing_feature_questions: job.missing_feature_questions || [],
        stage_warnings: job.stage_warnings || {},
        risk_score: job.risk_score || (job.final_plan_data && job.final_plan_data.risk_score) || "",
      });
      if (hasText(job.image_url)) {
        renderImage(job.image_url);
      }
      if (hasText(job.showcase_url)) {
        renderShowcase(job.showcase_url);
      }

      if (job.status === "queued") {
        setStatus("running", "排队中");
      } else if (job.status === "running") {
        setStatus("running", "运行中");
      } else if (job.status === "blocked") {
        setStatus("blocked", "需补全");
        window.setTimeout(refreshHistory, 700);
        scrollToCard("warnings");
        break;
      } else if (job.status === "done") {
        renderCulture(job.culture_data, job.culture_suggestion);
        renderRegulation(job.regulation_data, job.regulation_suggestion);
        renderDesign(job.design_data, job.design_suggestion);
        renderFinalPlan(job.final_plan_data, job.final_plan);
        renderImage(job.image_url);
        renderShowcase(job.showcase_url);
        setStatus("done", "完成");
        window.setTimeout(refreshHistory, 700);
        break;
      } else if (job.status === "error") {
        setStatus("error", "运行失败");
        planEl.textContent = job.error || "未知错误";
        window.setTimeout(refreshHistory, 700);
        break;
      }

      await sleep(800);
    }
  } catch (error) {
    setStatus("error", "请求失败");
    planEl.textContent = String(error);
    appendLogLine("请求失败，请检查服务日志。");
  } finally {
    setLoading(false);
  }
});

skipVisionInput.addEventListener("change", syncVisionFlags);

if (mockBtn) {
  mockBtn.addEventListener("click", () => {
    activePollToken += 1;
    setStatus("running", "模拟中");
    resetOutputs();
    const lines = [
      "启动本地化流程...",
      "CultureAgent 检索文化知识...",
      "RegulationAgent 查询法规合规项...",
      "DesignAgent 合并生成修改方案...",
      "CoordinatorAgent 产出最终计划...",
      "任务完成（模拟）",
    ];
    for (const line of lines) {
      appendLogLine(line);
    }
    setStatus("done", "模拟完成");
  });
}

if (clearBtn) {
  clearBtn.addEventListener("click", () => {
    activePollToken += 1;
    setLoading(false);
    setStatus("idle", "就绪");
    resetOutputs();
    scrollToCard("logs", "auto");
  });
}

if (countryAddBtn) {
  countryAddBtn.addEventListener("click", () => {
    addMarketOption(countryCustom.value);
  });
}

syncVisionFlags();
resetOutputs();
loadCountries();
refreshHistory();

if (historyRefreshBtn) {
  historyRefreshBtn.addEventListener("click", refreshHistory);
}

if (cardCarousel) {
  for (const btn of cardTabButtons) {
    btn.addEventListener("click", () => {
      const id = String(btn.dataset.cardTab || "");
      scrollToCard(id);
    });
  }

  if (cardPrevBtn) {
    cardPrevBtn.addEventListener("click", () => moveCard(-1));
  }
  if (cardNextBtn) {
    cardNextBtn.addEventListener("click", () => moveCard(1));
  }

  cardCarousel.addEventListener("scroll", () => {
    if (cardScrollRaf) {
      return;
    }
    cardScrollRaf = window.requestAnimationFrame(() => {
      cardScrollRaf = 0;
      updateActiveCardFromScroll();
    });
  });

  const cancelProgrammaticTarget = () => {
    programmaticTargetCardId = "";
    programmaticTargetUntil = 0;
  };

  cardCarousel.addEventListener("pointerdown", cancelProgrammaticTarget, { passive: true });
  cardCarousel.addEventListener("wheel", cancelProgrammaticTarget, { passive: true });

  updateActiveCardFromScroll();
}
