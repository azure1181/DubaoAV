const fmt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
const isFilePage = window.location.protocol === "file:";
const outputFolders = {
  2026: "output_forecast",
  2027: "Output_2027",
};

let selectedYear = "2026";

function value(id, text) {
  document.getElementById(id).textContent = text;
}

function flow(value) {
  return value == null ? "--" : fmt.format(value);
}

function staticDataForYear(year) {
  if (window.FORECAST_DATA_BY_YEAR && window.FORECAST_DATA_BY_YEAR[year]) {
    return window.FORECAST_DATA_BY_YEAR[year];
  }
  if (window.FORECAST_DATA && String(window.FORECAST_DATA.year || "2026") === String(year)) {
    return window.FORECAST_DATA;
  }
  return null;
}

function pickYearFromPayload(payload, year) {
  if (!payload) return null;
  if (payload[year]) return payload[year];
  if (payload[String(year)]) return payload[String(year)];
  if (String(payload.year || "") === String(year)) return payload;
  return null;
}

function drawChart(monthly, year, historicalMonthly = []) {
  const canvas = document.getElementById("flowChart");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const pad = { left: 62, right: 24, top: 24, bottom: 46 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const maxY =
    Math.ceil(
      Math.max(
        ...monthly.map((d) => d.forecast_flow_m3s || 0),
        ...monthly.map((d) => d.reference_flow_2025_m3s || 0),
        ...monthly.map((d) => d.historical_mean_m3s || 0),
        ...historicalMonthly.map((d) => d.flow_m3s || 0)
      ) / 25
    ) * 25 || 25;

  const x = (month) => pad.left + ((month - 1) / 11) * innerW;
  const y = (val) => pad.top + innerH - (val / maxY) * innerH;

  ctx.clearRect(0, 0, width, height);
  ctx.font = "14px Arial";
  ctx.strokeStyle = "#d9e0e4";
  ctx.fillStyle = "#697782";
  ctx.lineWidth = 1;

  for (let tick = 0; tick <= maxY; tick += 25) {
    const yy = y(tick);
    ctx.beginPath();
    ctx.moveTo(pad.left, yy);
    ctx.lineTo(width - pad.right, yy);
    ctx.stroke();
    ctx.fillText(String(tick), 16, yy + 4);
  }

  monthly.forEach((d) => {
    const xx = x(d.month);
    ctx.beginPath();
    ctx.moveTo(xx, pad.top);
    ctx.lineTo(xx, height - pad.bottom);
    ctx.stroke();
    ctx.fillText(String(d.month), xx - 4, height - 18);
  });

  const historicalByYear = historicalMonthly.reduce((acc, item) => {
    if (!item.year || !item.month || item.flow_m3s == null || Number(item.year) === 2025) return acc;
    const key = String(item.year);
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});

  Object.values(historicalByYear).forEach((items) => {
    const sorted = items.slice().sort((a, b) => a.month - b.month);
    if (sorted.length < 2) return;
    ctx.strokeStyle = "#aab7b8";
    ctx.lineWidth = 0.8;
    ctx.globalAlpha = 0.22;
    ctx.beginPath();
    sorted.forEach((d, idx) => {
      const xx = x(d.month);
      const yy = y(d.flow_m3s || 0);
      if (idx === 0) ctx.moveTo(xx, yy);
      else ctx.lineTo(xx, yy);
    });
    ctx.stroke();
    ctx.globalAlpha = 1;
  });

  function line(key, color, dash = []) {
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 3;
    ctx.setLineDash(dash);
    ctx.beginPath();
    monthly.forEach((d, idx) => {
      const xx = x(d.month);
      const yy = y(d[key] || 0);
      if (idx === 0) ctx.moveTo(xx, yy);
      else ctx.lineTo(xx, yy);
    });
    ctx.stroke();
    ctx.setLineDash([]);
    monthly.forEach((d) => {
      ctx.beginPath();
      ctx.arc(x(d.month), y(d[key] || 0), 5, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  line("forecast_flow_m3s", "#c0392b");
  line("reference_flow_2025_m3s", "#2874a6");
  line("historical_mean_m3s", "#566573", [8, 6]);

  ctx.fillStyle = "#1f2933";
  ctx.font = "13px Arial";
  ctx.fillText("Lịch sử", width - 390, 28);
  ctx.fillStyle = "#aab7b8";
  ctx.fillRect(width - 414, 18, 16, 4);
  ctx.fillStyle = "#1f2933";
  ctx.fillText(`Dự báo ${year}`, width - 288, 28);
  ctx.fillStyle = "#c0392b";
  ctx.fillRect(width - 312, 18, 16, 4);
  ctx.fillStyle = "#1f2933";
  ctx.fillText("Thực đo 2025", width - 180, 28);
  ctx.fillStyle = "#2874a6";
  ctx.fillRect(width - 204, 18, 16, 4);
}

function renderTable(monthly) {
  const rows = monthly
    .map(
      (d) => `
        <tr>
          <td>Tháng ${d.month}</td>
          <td>${flow(d.forecast_flow_m3s)}</td>
          <td>${flow(d.reference_flow_2025_m3s)}</td>
          <td>${flow(d.historical_mean_m3s)}</td>
          <td><span class="badge">${d.scenario || "--"}</span></td>
        </tr>
      `
    )
    .join("");
  document.getElementById("monthlyRows").innerHTML = rows;
}

function configureLinks(mode = "static", year = selectedYear) {
  const apiMode = mode === "api";
  const folder = outputFolders[year] || `Output_${year}`;
  const links = {
    jsonLink: apiMode ? `/api/forecast?year=${year}` : "./forecast-data.json",
    excelLink: apiMode
      ? `/download/${year}/bao_cao_du_bao_${year}.xlsx`
      : `../${folder}/bao_cao_du_bao_${year}.xlsx`,
    chartLink: apiMode
      ? `/download/${year}/du_bao_nuoc_ve_${year}.png`
      : `../${folder}/du_bao_nuoc_ve_${year}.png`,
  };

  Object.entries(links).forEach(([id, href]) => {
    const node = document.getElementById(id);
    if (node) node.href = href;
  });

  const image = document.querySelector(".report-image");
  if (image) {
    image.src = apiMode ? `/chart.png?year=${year}` : `../${folder}/du_bao_nuoc_ve_${year}.png`;
    image.alt = `Biểu đồ dự báo lưu lượng nước về năm ${year}`;
  }
}

function setActiveYear(year) {
  selectedYear = String(year);
  document.querySelectorAll(".year-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.year === selectedYear);
  });
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} trả về ${response.status}`);
  }
  return response.json();
}

async function getReport(year) {
  configureLinks("static", year);

  const loadStatic = async () => {
    const inlineReport = staticDataForYear(year);
    if (inlineReport) return inlineReport;
    const payload = await fetchJson("./forecast-data.json");
    const report = pickYearFromPayload(payload, year);
    if (report) return report;
    throw new Error(`Không có dữ liệu tĩnh cho năm ${year}`);
  };

  if (isFilePage) {
    return { report: await loadStatic(), mode: "static" };
  }

  try {
    return { report: await fetchJson(`/api/forecast?year=${year}`), mode: "api" };
  } catch (apiError) {
    return { report: await loadStatic(), mode: "static" };
  }
}

async function loadReport(year = selectedYear) {
  setActiveYear(year);
  const { report, mode } = await getReport(selectedYear);
  configureLinks(mode, selectedYear);

  const s = report.summary;

  document.title = `Dự báo nước về hồ A Vương ${selectedYear}`;
  value("pageTitle", `Dự báo nước về hồ A Vương năm ${selectedYear}`);
  value("forecastMetricLabel", `Dự báo TB ${selectedYear}`);
  value("forecastMean", flow(s.forecast_mean_m3s));
  value("historyMean", flow(s.historical_mean_m3s));
  value("scenario", s.scenario);
  value("peakMonth", `Tháng ${s.peak_month}`);
  value("peakFlow", `${flow(s.peak_flow_m3s)} m3/s`);
  value("generatedAt", `Cập nhật: ${new Date(report.generated_at).toLocaleString("vi-VN")}`);
  value("comment", report.executive_comment || "Chưa có nhận xét.");

  drawChart(report.monthly, selectedYear, report.historical_monthly || []);
  renderTable(report.monthly);
}

document.querySelectorAll(".year-button").forEach((button) => {
  button.addEventListener("click", () => {
    loadReport(button.dataset.year).catch(showError);
  });
});

function showError(error) {
  value("generatedAt", "Không tải được dữ liệu");
  value(
    "comment",
    `${error.message}. Nếu đang mở trực tiếp file HTML, hãy chạy: python api_website.py --export-json để tạo lại dữ liệu tĩnh.`
  );
}

loadReport(selectedYear).catch(showError);
