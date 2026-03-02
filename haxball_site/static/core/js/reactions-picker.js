(function () {
  function createReactionsPicker(initialGroupId) {
    return {
      activeGroupId: initialGroupId || '',
      searchQuery: '',
      _syncScheduled: false,

      scrollToGroup(groupId) {
        const container = this.$refs.groups;
        const group = container?.querySelector("[data-reaction-group='" + groupId + "']");
        if (!container || !group) {
          return;
        }

        this.activeGroupId = groupId;

        const offset = Math.max(0, group.offsetTop - container.offsetTop + 1);
        container.scrollTop = offset;
      },

      syncActiveGroup() {
        const container = this.$refs.groups;
        if (!container) {
          return;
        }

        const groups = container.querySelectorAll('[data-reaction-group]:not(.tw\\:hidden)');
        if (!groups.length) {
          return;
        }
        const marker = container.scrollTop + 8;
        let current = groups[0];

        groups.forEach((group) => {
          const offset = group.offsetTop - container.offsetTop;
          if (offset <= marker) {
            current = group;
          }
        });

        const groupId = current?.dataset?.reactionGroup;
        if (groupId) {
          this.activeGroupId = groupId;
        }
      },

      scheduleSyncActiveGroup() {
        if (this._syncScheduled) {
          return;
        }

        this._syncScheduled = true;
        requestAnimationFrame(() => {
          this._syncScheduled = false;
          this.syncActiveGroup();
        });
      },

      filterEmojis() {
        const container = this.$refs.groups;
        if (!container) {
          return;
        }

        const query = this.searchQuery.trim().toLowerCase();
        const groups = container.querySelectorAll('[data-reaction-group]');

        groups.forEach((group) => {
          let visibleCount = 0;
          const emojis = group.querySelectorAll('[data-reaction-item]');

          emojis.forEach((emojiButton) => {
            if (!query) {
              emojiButton.classList.remove('tw:hidden');
              visibleCount += 1;
              return;
            }

            const label = (emojiButton.dataset.reactionLabel || '').toLowerCase();
            const code = (emojiButton.dataset.reactionCode || '').toLowerCase();
            const matches = label.includes(query) || code.includes(query);
            emojiButton.classList.toggle('tw:hidden', !matches);
            if (matches) {
              visibleCount += 1;
            }
          });

          group.classList.toggle('tw:hidden', visibleCount === 0);
        });

        const firstVisible = container.querySelector('[data-reaction-group]:not(.tw\\:hidden)');
        if (firstVisible?.dataset?.reactionGroup) {
          this.activeGroupId = firstVisible.dataset.reactionGroup;
        }
      },
    };
  }

  window.createReactionsPicker = createReactionsPicker;
})();
