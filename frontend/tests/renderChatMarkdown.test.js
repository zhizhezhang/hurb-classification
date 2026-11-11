import test from 'node:test'
import assert from 'node:assert/strict'
import { renderChatMarkdown } from '../src/utils/renderChatMarkdown.js'

test('assistant Markdown renders paragraphs, line breaks, bold text, and lists', () => {
  const html = renderChatMarkdown('第一段\n第二行\n\n**注意**事项：\n\n- 第一项\n- 第二项')
  assert.match(html, /<p>第一段<br>\n第二行<\/p>/)
  assert.match(html, /<strong>注意<\/strong>/)
  assert.match(html, /<ul>[\s\S]*<li>第一项<\/li>[\s\S]*<li>第二项<\/li>[\s\S]*<\/ul>/)
})

test('assistant Markdown escapes raw HTML and rejects unsafe links', () => {
  const html = renderChatMarkdown('<script>alert(1)</script>\n\n[点击](javascript:alert(1))\n\n![图](https://example.com/a.png)')
  assert.doesNotMatch(html, /<script|href="javascript:|<img/i)
  assert.match(html, /&lt;script&gt;/)
})
