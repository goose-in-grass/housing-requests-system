// Блокировка кнопки отправки после нажатия (защита от дублей при двойном клике).
document.addEventListener("submit", function (e) {
  var form = e.target;
  if (form.dataset.confirm && !form.dataset.confirmed) {
    e.preventDefault();
    var modalEl = document.getElementById("confirmModal");
    document.getElementById("confirmBody").textContent = form.dataset.confirm;
    var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    var ok = document.getElementById("confirmOk");
    ok.onclick = function () { form.dataset.confirmed = "1"; modal.hide(); form.requestSubmit(); };
    modal.show();
    return;
  }
  form.querySelectorAll("button[type=submit], button:not([type])").forEach(function (b) {
    setTimeout(function () { b.disabled = true; }, 0);
  });
});
