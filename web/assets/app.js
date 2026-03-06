const form = document.getElementById("run-form");
const countrySelect = document.getElementById("country");
const countryCustom = document.getElementById("country-custom");
const skipVisionInput = document.getElementById("skip-vision");
const auto3dInput = document.getElementById("auto-3d");
const runBtn = document.getElementById("run-btn");
const runBtnText = document.getElementById("run-btn-text");
const statusPill = document.getElementById("status-pill");

const logsEl = document.getElementById("logs");
const planEl = document.getElementById("final-plan");
const imageWrap = document.getElementById("image-wrap");
const showcaseWrap = document.getElementById("showcase-wrap");

function setStatus(kind, text) {
  statusPill.className = `status ${kind}`;
  statusPill.textContent = text;
}

function setLoading(loading) {
  runBtn.disabled = loading;
  runBtnText.textContent = loading ? "生成中..." : "开始生成";
}

function resetMedia() {
  imageWrap.className = "media-wrap empty";
  imageWrap.textContent = "暂无图片";
  showcaseWrap.className = "media-wrap empty";
  showcaseWrap.textContent = "暂无展示结果";
}

function renderImage(url) {
  if (!url) {
    return;
  }
  const img = document.createElement("img");
  img.src = url;
  img.alt = "concept";
  imageWrap.className = "media-wrap";
  imageWrap.textContent = "";
  imageWrap.appendChild(img);
}

function renderShowcase(url) {
  if (!url) {
    return;
  }

  showcaseWrap.className = "media-wrap";
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

function syncVisionFlags() {
  if (skipVisionInput.checked) {
    auto3dInput.checked = false;
    auto3dInput.disabled = true;
  } else {
    auto3dInput.disabled = false;
  }
}

async function loadCountries() {
  try {
    const response = await fetch("/api/countries");
    const data = await response.json();
    const countries = data.countries || [];

    countrySelect.innerHTML = "";
    for (const country of countries) {
      const option = document.createElement("option");
      option.value = country;
      option.textContent = country;
      countrySelect.appendChild(option);
    }
  } catch (error) {
    countrySelect.innerHTML = '<option value="japan">japan</option>';
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

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

  setLoading(true);
  setStatus("running", "运行中");
  resetMedia();
  logsEl.textContent = "执行中，请稍候...";
  planEl.textContent = "生成中...";

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        country: countryInput,
        description,
        skip_vision: skipVisionInput.checked,
        auto_3d: auto3dInput.checked,
      }),
    });

    const data = await response.json();
    logsEl.textContent = (data.logs || []).join("\n") || "无日志";

    if (!data.success) {
      setStatus("error", "运行失败");
      planEl.textContent = data.error || "未知错误";
      return;
    }

    planEl.textContent = data.final_plan || "无最终方案";
    renderImage(data.image_url);
    renderShowcase(data.showcase_url);
    setStatus("done", "完成");
  } catch (error) {
    setStatus("error", "请求失败");
    planEl.textContent = String(error);
    logsEl.textContent = "请求失败，请检查服务日志。";
  } finally {
    setLoading(false);
  }
});

skipVisionInput.addEventListener("change", syncVisionFlags);

syncVisionFlags();
loadCountries();
