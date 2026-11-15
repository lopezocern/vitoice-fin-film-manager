import { describe, it, expect } from 'vitest';
import { isEditableTarget, moveCursor, resolveNavKey } from './keyboardNav';

describe('resolveNavKey', () => {
  it('maps j/k and arrows to next/prev', () => {
    expect(resolveNavKey({ key: 'j' })).toBe('next');
    expect(resolveNavKey({ key: 'ArrowDown' })).toBe('next');
    expect(resolveNavKey({ key: 'k' })).toBe('prev');
    expect(resolveNavKey({ key: 'ArrowUp' })).toBe('prev');
  });

  it('maps space to toggle and x to toggle-all', () => {
    expect(resolveNavKey({ key: ' ' })).toBe('toggle');
    expect(resolveNavKey({ key: 'x' })).toBe('toggleAll');
    expect(resolveNavKey({ key: 'X' })).toBe('toggleAll');
  });

  it('maps Enter / e / i to open / edit / ignore', () => {
    expect(resolveNavKey({ key: 'Enter' })).toBe('open');
    expect(resolveNavKey({ key: 'e' })).toBe('edit');
    expect(resolveNavKey({ key: 'i' })).toBe('ignore');
  });

  it('ignores modifier combinations so browser shortcuts still work', () => {
    expect(resolveNavKey({ key: 'j', ctrlKey: true })).toBe('none');
    expect(resolveNavKey({ key: 'x', metaKey: true })).toBe('none');
    expect(resolveNavKey({ key: 'k', altKey: true })).toBe('none');
  });

  it('ignores unrelated keys', () => {
    expect(resolveNavKey({ key: 'q' })).toBe('none');
    expect(resolveNavKey({ key: 'Escape' })).toBe('none');
    expect(resolveNavKey({ key: 'Tab' })).toBe('none');
  });
});

describe('moveCursor', () => {
  it('returns -1 for an empty list', () => {
    expect(moveCursor(0, 1, 0)).toBe(-1);
    expect(moveCursor(-1, -1, 0)).toBe(-1);
  });

  it('enters at the correct end when no cursor yet', () => {
    expect(moveCursor(-1, 1, 20)).toBe(0);
    expect(moveCursor(-1, -1, 20)).toBe(19);
  });

  it('clamps at both ends instead of wrapping', () => {
    expect(moveCursor(0, -1, 20)).toBe(0);
    expect(moveCursor(19, 1, 20)).toBe(19);
  });

  it('moves by delta within bounds', () => {
    expect(moveCursor(5, 1, 20)).toBe(6);
    expect(moveCursor(5, -1, 20)).toBe(4);
  });

  it('handles single-item lists', () => {
    expect(moveCursor(-1, 1, 1)).toBe(0);
    expect(moveCursor(0, 1, 1)).toBe(0);
  });
});

describe('isEditableTarget', () => {
  it('detects inputs, textareas and selects', () => {
    expect(isEditableTarget({ tagName: 'INPUT' })).toBe(true);
    expect(isEditableTarget({ tagName: 'textarea' })).toBe(true);
    expect(isEditableTarget({ tagName: 'SELECT' })).toBe(true);
  });

  it('detects contenteditable', () => {
    expect(isEditableTarget({ tagName: 'DIV', isContentEditable: true })).toBe(true);
  });

  it('lets plain elements and null through', () => {
    expect(isEditableTarget({ tagName: 'DIV' })).toBe(false);
    expect(isEditableTarget({ tagName: 'BUTTON' })).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
  });
});
