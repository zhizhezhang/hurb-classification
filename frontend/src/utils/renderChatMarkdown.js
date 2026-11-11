import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false })
markdown.disable('image')

export function renderChatMarkdown(text) {
  return markdown.render(typeof text === 'string' ? text : '')
}
