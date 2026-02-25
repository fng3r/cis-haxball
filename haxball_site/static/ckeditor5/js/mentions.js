window.fetchMentions = function(queryText) {
    if (!queryText || !queryText.trim()) {
        return Promise.resolve([]);
    }

    return fetch('/api/users/search?query=' + encodeURIComponent(queryText), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin'
    })
    .then(response => {
        if (!response.ok) {
            return [];
        }

        return response.json();
    })
    .then(items => {
        if (!Array.isArray(items)) {
            return [];
        }

        return items.map(item => {
            const mentionId = '@' + item.username;
            return {
                id: mentionId,
                text: mentionId,
                username: item.username,
                userId: item.id,
                link: item.link,
                avatar: item.avatar
            };
        });
    })
    .catch(() => []);
};

window.renderMentionItem = function(item) {
    const container = document.createElement('span');
    container.className = 'tw:flex tw:items-center tw:gap-x-2';

    if (item.avatar) {
      const avatar = document.createElement('img');
      avatar.src = item.avatar;
      avatar.className = 'tw:size-6! tw:rounded-full';
      avatar.alt = '';
      container.appendChild(avatar);
    }

    const label = document.createElement('span');
    label.className = 'tw:text-black/80 tw:truncate';
    label.textContent = item.username;
    container.appendChild(label);

    return container;
};