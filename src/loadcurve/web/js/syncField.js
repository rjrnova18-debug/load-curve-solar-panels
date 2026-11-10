// Showing a state value in a form field without overwriting what the user typed.

const shown = new WeakMap(); // field -> the state value it was last given

/**
 * Write value into field, unless the user is typing there (the field has focus)
 * or the state still holds the value the field was last given. The second rule
 * keeps an invalid entry visible, with its invalid mark, until the user fixes it
 * or the state changes for another reason (an opened study, a lookup).
 */
export function syncField(field, value, format = String) {
  if (field.ownerDocument.activeElement === field) return;
  if (shown.has(field) && Object.is(shown.get(field), value)) return;
  shown.set(field, value);
  field.value = format(value);
  field.removeAttribute("aria-invalid");
}

/** Record that field already shows value, because the user just typed it. */
export function fieldShows(field, value) {
  shown.set(field, value);
}
