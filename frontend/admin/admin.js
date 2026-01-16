const API = "http://127.0.0.1:8000";

function show(preId, data) {
  document.getElementById(preId).textContent =
    typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

async function apiGet(path) {
  const res = await fetch(`${API}${path}`);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

async function apiPost(path, bodyObj) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bodyObj)
  });

  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

/* ------------------- PING ------------------- */
document.getElementById("btnPing").addEventListener("click", async () => {
  const r = await apiGet("/");
  show("pingOut", r);
});

/* ------------------- STUDENTS ------------------- */
document.getElementById("btnImportStudents").addEventListener("click", async () => {
  const r = await apiPost("/students/import", {});
  show("studentsOut", r);
});

document.getElementById("btnGetStudents").addEventListener("click", async () => {
  const r = await apiGet("/students");
  show("studentsOut", r);
});

/* ------------------- CLASSROOMS ------------------- */
document.getElementById("classroomForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const room_id = document.getElementById("roomId").value.trim();
  const seats_per_bench = Number(document.getElementById("seatsPerBench").value);
  const layoutText = document.getElementById("layoutJson").value.trim();

  let layout;
  try {
    layout = JSON.parse(layoutText);
  } catch (err) {
    show("classroomsOut", "Layout JSON invalid. Example: {\"1\":4,\"2\":5}");
    return;
  }

  const r = await apiPost("/classrooms/create", { room_id, seats_per_bench, layout });
  show("classroomsOut", r);
});

document.getElementById("btnGetClassrooms").addEventListener("click", async () => {
  const r = await apiGet("/classrooms");
  show("classroomsOut", r);
});

/* ------------------- EXAMS ------------------- */
document.getElementById("examForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const exam_name = document.getElementById("examName").value.trim();
  const exam_date = document.getElementById("examDate").value.trim() || null;
  const session = document.getElementById("examSession").value.trim() || null;

  const r = await apiPost("/exams/create", { exam_name, exam_date, session });
  show("examOut", r);
});

// View all exams
document.getElementById("btnGetExams").addEventListener("click", async () => {
  const r = await apiGet("/exams");
  show("examOut", r);
});

/* ------------------- REGISTER ------------------- */
document.getElementById("registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const examId = Number(document.getElementById("regExamId").value);
  const year = Number(document.getElementById("regYear").value);

  const r = await apiPost(`/exams/${examId}/register/year`, { year });
  show("registerOut", r);
});

// View registrations
document.getElementById("btnViewRegistrations").addEventListener("click", async () => {
  const examId = Number(document.getElementById("regExamId").value);
  if (!examId) return show("registerOut", "Enter Exam ID to view registrations");

  const r = await apiGet(`/exams/${examId}/registrations`);
  show("registerOut", r);
});

/* ------------------- ALLOCATE ------------------- */
document.getElementById("allocateForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const exam_id = Number(document.getElementById("allocExamId").value);
  const room_id = document.getElementById("allocRoomId").value.trim();

  const r = await apiPost("/allocate", { exam_id, room_id });
  show("allocateOut", r);
});

// View allocations
document.getElementById("btnViewAllocations").addEventListener("click", async () => {
  const examId = Number(document.getElementById("allocExamId").value);
  const roomId = document.getElementById("allocRoomId").value.trim();

  if (!examId) return show("allocateOut", "Enter Exam ID to view allocations");

  const path = roomId
    ? `/exams/${examId}/allocations?room_id=${encodeURIComponent(roomId)}`
    : `/exams/${examId}/allocations`;

  const r = await apiGet(path);
  show("allocateOut", r);
});

/* ------------------- EXPORT ------------------- */
document.getElementById("btnExportExcel").addEventListener("click", async () => {
  const room_id = document.getElementById("exportRoomId").value.trim();
  if (!room_id) return show("allocateOut", "Enter Export Room ID");

  window.open(`${API}/export/allocation/excel?room_id=${encodeURIComponent(room_id)}`, "_blank");
});

document.getElementById("btnExportPdf").addEventListener("click", async () => {
  const room_id = document.getElementById("exportRoomId").value.trim();
  if (!room_id) return show("allocateOut", "Enter Export Room ID");

  window.open(`${API}/export/allocation/pdf?room_id=${encodeURIComponent(room_id)}`, "_blank");
});

function getSelectedRooms() {
  const checkboxes = document.querySelectorAll(".roomCheck:checked");
  return Array.from(checkboxes).map(cb => cb.value);
}

async function loadRooms() {
  const r = await apiGet("/classrooms");
  if (!r.ok) {
    show("allocateOut", r);
    return;
  }

  const roomsDiv = document.getElementById("roomsList");
  roomsDiv.innerHTML = "";

  const rooms = Array.isArray(r.data) ? r.data : (r.data.data || []);

  rooms.forEach((c) => {
    const label = document.createElement("label");
    label.innerHTML = `
      <input type="checkbox" class="roomCheck" value="${c.room_id}">
      ${c.room_id} (${c.seats_per_bench} seats/bench)
    `;
    roomsDiv.appendChild(label);
  });

  show("allocateOut", "Rooms loaded. Select rooms and allocate.");
}


document.getElementById("btnLoadRooms").addEventListener("click", loadRooms);

document.getElementById("btnCapacityCheck").addEventListener("click", async () => {
  const exam_id = Number(document.getElementById("allocExamId").value);
  if (!exam_id) return show("allocateOut", "Enter Exam ID first");

  const rooms = getSelectedRooms();
  if (rooms.length === 0) return show("allocateOut", "Select at least one room");

  const r = await apiPost("/capacity-check/multi", { exam_id, rooms });
  show("allocateOut", r);
});

document.getElementById("btnAllocateMulti").addEventListener("click", async () => {
  const exam_id = Number(document.getElementById("allocExamId").value);
  if (!exam_id) return show("allocateOut", "Enter Exam ID first");

  const rooms = getSelectedRooms();
  if (rooms.length === 0) return show("allocateOut", "Select at least one room");

  const r = await apiPost("/allocate/multi", { exam_id, rooms });
  show("allocateOut", r);
});
