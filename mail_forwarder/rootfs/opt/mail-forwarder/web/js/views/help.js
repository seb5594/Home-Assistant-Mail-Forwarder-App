// Help: the short version, a glossary and answers to the questions beginners ask most.
import { h } from '../dom.js';
import { pairs, richList, t } from '../i18n.js';

function definitionList(items) {
  return h('dl', { class: 'definitions' }, items.flatMap(([term, text]) => [
    h('dt', null, term), h("dd", null, rich_text(text))]));
}

// Glossary and FAQ answers are plain text with `code` markup.
function rich_text(text) {
  return text.split(/(`.+?`)/g).filter(Boolean).map((part) => (part.startsWith('`') ? h('code', null, part.slice(1, -1)) : part));
}

function section(titleKey, items) {
  return h('section', { class: 'card' }, h('h2', null, t(titleKey)), definitionList(pairs(items)));
}

export function renderHelp(ctx) {
  return h('div', { class: 'grid' },
    h('section', { class: 'card' }, h('h2', null, t('help.start.title')),
      h('ol', { class: 'how' }, richList('help.start.steps').map((nodes) => h('li', null, nodes))),
      h('div', { class: 'row', style: 'margin-top:12px' },
        h('button', { class: 'button', type: 'button', onclick: () => ctx.navigate('overview') }, t('common.go_overview')))),
    section('help.glossary.title', 'help.glossary.items'),
    section('help.faq.title', 'help.faq.items'),
    section('help.trouble.title', 'help.trouble.items'));
}
