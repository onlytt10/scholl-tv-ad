const search = document.getElementById('search');
const filter = document.getElementById('filter');
function filterRows() {
  let visible = 0;
  document.querySelectorAll('.media-row').forEach(row => {
    row.hidden = !(row.dataset.title.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()) && (filter.value === 'any' || filter.value === row.dataset.grade));
    if (!row.hidden) visible++;
  });
  document.getElementById('no-results').hidden = visible > 0 || !document.querySelector('.media-row');
  updateHandles();
}
search?.addEventListener('input', filterRows);
filter?.addEventListener('change', filterRows);
document.getElementById('file')?.addEventListener('change', event => {
  const file = event.target.files[0];
  document.getElementById('selected-file').textContent = file ? file.name : '';
});
document.getElementById('upload-form')?.addEventListener('submit', () => {
  const button = document.getElementById('upload-button');
  button.disabled = true; button.textContent = '업로드 중…';
  document.getElementById('upload-status').textContent = '파일 크기에 따라 시간이 걸릴 수 있어요. 잠시 기다려 주세요.';
});
const dialog = document.getElementById('delete-dialog');
let deleteTrigger;
document.querySelectorAll('.delete-trigger').forEach(link => link.addEventListener('click', event => {
  if (typeof dialog?.showModal !== 'function') return;
  event.preventDefault(); deleteTrigger = link;
  document.getElementById('delete-name').textContent = link.dataset.name;
  document.getElementById('delete-form').action = link.href;
  dialog.showModal();
  document.getElementById('cancel-delete').focus();
}));
document.getElementById('cancel-delete')?.addEventListener('click', () => dialog.close());
dialog?.addEventListener('close', () => deleteTrigger?.focus());

const playlist = document.getElementById('playlist');
const reorderStatus = document.getElementById('reorder-status');
let moving = null, saving = false, scrollFrame = 0;
const rows = () => [...(playlist?.querySelectorAll('.media-row') || [])];
function renumber() { rows().forEach((row, i) => { row.querySelector('.order').textContent = i + 1; }); }
function updateHandles() {
  const filtered = Boolean(search?.value) || (filter && filter.value !== 'any');
  rows().forEach(row => { row.querySelector('.drag-handle').disabled = saving || filtered || rows().length < 2; });
  const help = document.getElementById('reorder-help');
  if (help) help.textContent = filtered ? '순서를 바꾸려면 검색을 지우고 전체 대상을 선택해 주세요.' : '왼쪽 ⠿ 손잡이를 잡고 드래그하면 순서가 바로 저장돼요.';
}
function beginMove(row, handle, pointer = null) {
  if (moving || saving || handle.disabled) return false;
  moving = { row, handle, original: rows(), pointer, y: null };
  row.classList.add('dragging'); handle.setAttribute('aria-pressed', 'true');
  search.disabled = true; filter.disabled = true;
  reorderStatus.textContent = '원하는 위치로 이동하세요. Esc를 누르면 취소돼요.';
  return true;
}
function placeAt(y) {
  if (!moving) return;
  const otherRows = rows().filter(row => row !== moving.row);
  const before = otherRows.find(row => { const rect = row.getBoundingClientRect(); return y < rect.top + rect.height / 2; });
  playlist.insertBefore(moving.row, before || null);
  if (moving.pointer !== null) moving.handle.setPointerCapture(moving.pointer);
  renumber();
}
function autoScroll() {
  if (!moving || moving.pointer === null) return;
  const y = moving.y;
  if (y !== null) {
    const delta = y < 90 ? -12 : y > window.innerHeight - 90 ? 12 : 0;
    if (delta) { window.scrollBy(0, delta); placeAt(y); }
  }
  scrollFrame = requestAnimationFrame(autoScroll);
}
async function finishMove(cancel = false) {
  if (!moving) return;
  const move = moving; moving = null; cancelAnimationFrame(scrollFrame);
  move.row.classList.remove('dragging'); move.handle.setAttribute('aria-pressed', 'false');
  if (move.pointer !== null && move.handle.hasPointerCapture(move.pointer)) move.handle.releasePointerCapture(move.pointer);
  const restore = () => { move.original.forEach(row => playlist.append(row)); renumber(); };
  if (cancel) { restore(); reorderStatus.textContent = '순서 변경을 취소했어요.'; }
  else {
    const order = rows().map(row => row.dataset.name);
    const original = move.original.map(row => row.dataset.name);
    if (order.some((name, i) => name !== original[i])) {
      saving = true; updateHandles();
      reorderStatus.textContent = '순서를 저장하고 있어요…';
      try {
        if (document.body.dataset.preview === 'true') {
          reorderStatus.textContent = '미리보기 순서를 변경했어요. 실제 광고에는 영향을 주지 않아요.';
        } else {
          const data = new FormData(); data.set('csrf', playlist.dataset.csrf);
          order.forEach(name => data.append('order', name)); original.forEach(name => data.append('original', name));
          const response = await fetch(playlist.dataset.reorderUrl, { method: 'POST', body: data });
          const result = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(result.error || '저장하지 못했어요. 연결을 확인하고 새로고침해 주세요.');
          reorderStatus.textContent = '재생 순서를 저장했어요.';
        }
      } catch (error) {
        restore(); reorderStatus.textContent = error.message || '저장하지 못해 이전 순서로 되돌렸어요.';
      } finally { saving = false; }
    } else reorderStatus.textContent = '순서가 그대로예요.';
  }
  search.disabled = false; filter.disabled = false; updateHandles(); move.handle.focus({ preventScroll: true });
}
playlist?.addEventListener('pointerdown', event => {
  const handle = event.target.closest('.drag-handle');
  if (!handle || !event.isPrimary || event.button !== 0) return;
  if (!beginMove(handle.closest('.media-row'), handle, event.pointerId)) return;
  event.preventDefault(); handle.focus(); handle.setPointerCapture(event.pointerId);
  moving.y = event.clientY; autoScroll();
});
playlist?.addEventListener('pointermove', event => {
  if (!moving || moving.pointer !== event.pointerId) return;
  moving.y = event.clientY; placeAt(event.clientY);
});
playlist?.addEventListener('pointerup', event => { if (moving?.pointer === event.pointerId) finishMove(); });
playlist?.addEventListener('pointercancel', event => { if (moving?.pointer === event.pointerId) finishMove(true); });
playlist?.addEventListener('lostpointercapture', event => { if (moving?.pointer === event.pointerId) finishMove(true); });
playlist?.addEventListener('keydown', event => {
  const handle = event.target.closest('.drag-handle');
  if (!handle) return;
  if (!moving && [' ', 'Enter'].includes(event.key)) { event.preventDefault(); beginMove(handle.closest('.media-row'), handle); return; }
  if (!moving || moving.pointer !== null) return;
  if ([' ', 'Enter'].includes(event.key)) { event.preventDefault(); finishMove(); }
  else if (['ArrowUp', 'ArrowDown'].includes(event.key)) {
    event.preventDefault();
    const row = moving.row;
    if (event.key === 'ArrowUp' && row.previousElementSibling) playlist.insertBefore(row, row.previousElementSibling);
    if (event.key === 'ArrowDown' && row.nextElementSibling) playlist.insertBefore(row.nextElementSibling, row);
    renumber(); handle.focus(); row.scrollIntoView({ block: 'nearest' });
    reorderStatus.textContent = `${row.querySelector('.order').textContent}번째 위치. Enter로 저장, Esc로 취소하세요.`;
  }
});
document.addEventListener('keydown', event => { if (event.key === 'Escape' && moving) { event.preventDefault(); finishMove(true); } });
playlist?.addEventListener('click', event => { if (moving || saving) { event.preventDefault(); event.stopImmediatePropagation(); } }, true);
updateHandles();
