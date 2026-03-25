const form = document.getElementById("fusion-form");
const resultMeta = document.getElementById("result-meta");
const previewTableHead = document.querySelector("#preview-table thead");
const previewTableBody = document.querySelector("#preview-table tbody");
const stopPollingButton = document.getElementById("stop-polling");

let pollingTimer = null;

function setResultMeta(payload) {
  resultMeta.textContent = JSON.stringify(payload, null, 2);
}

function clearPreviewTable() {
  previewTableHead.innerHTML = "";
  previewTableBody.innerHTML = "";
}

function renderPreviewRows(rows) {
  clearPreviewTable();

  if (!rows || rows.length === 0) {
    return;
  }

  const columns = Object.keys(rows[0]);

  const headerRow = document.createElement("tr");
  for (const column of columns) {
    const th = document.createElement("th");
    th.textContent = column;
    headerRow.appendChild(th);
  }
  previewTableHead.appendChild(headerRow);

  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const column of columns) {
      const td = document.createElement("td");
      const value = row[column];
      td.textContent = value === null || value === undefined ? "" : String(value);
      tr.appendChild(td);
    }
    previewTableBody.appendChild(tr);
  }
}

async function runFusionSubmission() {
  const payload = {
    input_source: document.getElementById("input_source").value,
    use_latest_from_prefix: document.getElementById("use_latest_from_prefix").checked,
    source_bucket: document.getElementById("source_bucket").value.trim(),
    source_prefix: document.getElementById("source_prefix").value.trim(),
    last_seen_key: document.getElementById("last_seen_key").value.trim(),
    input_s3_uri: document.getElementById("input_s3_uri").value.trim(),
    local_input_path: document.getElementById("local_input_path").value.trim(),
    fusion_method: document.getElementById("fusion_method").value,
    model_artifact_uri: document.getElementById("model_artifact_uri").value.trim(),
    output_s3_uri: document.getElementById("output_s3_uri").value.trim(),
    output_bucket: document.getElementById("output_bucket").value.trim(),
    output_prefix: document.getElementById("output_prefix").value.trim(),
    local_output_path: document.getElementById("local_output_path").value.trim(),
    write_output_to_s3: document.getElementById("write_output_to_s3").checked,
    write_output_local: document.getElementById("write_output_local").checked,
  };

  setResultMeta({ status: "running", message: "Submitting fusion job..." });

  try {
    const response = await fetch("/api/run-s3-fusion", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      setResultMeta({ status: "error", ...data });
      clearPreviewTable();
      return;
    }

    const {
      preview,
      ...meta
    } = data;

    if (meta.latest_source_key) {
      const lastSeenInput = document.getElementById("last_seen_key");
      lastSeenInput.value = String(meta.latest_source_key);
    }

    setResultMeta({ status: "success", ...meta });
    renderPreviewRows(preview || []);
  } catch (error) {
    setResultMeta({
      status: "error",
      error: error instanceof Error ? error.message : String(error),
    });
    clearPreviewTable();
  }
}

function stopPolling() {
  if (pollingTimer !== null) {
    window.clearInterval(pollingTimer);
    pollingTimer = null;
    setResultMeta({ status: "idle", message: "Auto polling stopped." });
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  stopPolling();
  await runFusionSubmission();

  const enablePolling = document.getElementById("enable_polling").checked;
  if (!enablePolling) {
    return;
  }

  const intervalRaw = Number(document.getElementById("poll_interval_seconds").value || 15);
  const intervalSeconds = Number.isFinite(intervalRaw) ? Math.max(3, intervalRaw) : 15;
  const intervalMs = intervalSeconds * 1000;

  setResultMeta({
    status: "polling",
    message: `Auto polling every ${intervalSeconds}s.`,
  });

  pollingTimer = window.setInterval(async () => {
    await runFusionSubmission();
  }, intervalMs);
});

stopPollingButton.addEventListener("click", () => {
  stopPolling();
});