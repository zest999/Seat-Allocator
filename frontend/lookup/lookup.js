const API = "http://127.0.0.1:8000";

function show(data) {
  document.getElementById("output").textContent =
    typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

document.getElementById("btnSearch").addEventListener("click", async () => {
  const examId = Number(document.getElementById("examId").value);
  const stuId = Number(document.getElementById("stuId").value);

  if (!examId || !stuId) {
    show("❌ Please enter both Exam ID and Register Number");
    return;
  }

  try {
    const res = await fetch(
      `${API}/public/seat-lookup?exam_id=${encodeURIComponent(examId)}&stu_id=${encodeURIComponent(stuId)}`
    );

    const data = await res.json();
    show(data);
  } catch (err) {
    show("❌ Could not connect to backend. Is FastAPI running?");
  }
});
