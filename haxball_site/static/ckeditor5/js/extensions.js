(function () {
  function ensureArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function registerMentionUpcast(editor) {
    if (!editor.plugins.has('Mention') || editor.__legacyMentionUpcastPatched) {
      return;
    }
    editor.__legacyMentionUpcastPatched = true;

    const mentionPlugin = editor.plugins.get('Mention');

    const mentionToModel = (viewItem) =>
      mentionPlugin.toMentionAttribute(viewItem, {
        link: viewItem.getAttribute('href'),
        userId: viewItem.getAttribute('data-mentioned-user-id'),
      });

    // Upcast legacy anchor-shaped mentions back into Mention model attribute (docs-style).
    editor.conversion.for('upcast').elementToAttribute({
      view: {
        name: 'a',
        key: 'data-mention',
        classes: 'mention tw:mention',
        attributes: {
          href: true,
          'data-mention': true,
          'data-mentioned-user-id': true,
        },
      },
      model: {
        key: 'mention',
        value: mentionToModel,
      },
      converterPriority: 'high',
    });

  }

  function registerMentionDowncast(editor) {
    if (!editor.plugins.has('Mention') || editor.__legacyMentionDowncastPatched) {
      return;
    }
    editor.__legacyMentionDowncastPatched = true;

    editor.conversion.for('downcast').attributeToElement({
      model: 'mention',
      view: (modelAttributeValue, { writer }) => {
        if (!modelAttributeValue) {
          return null;
        }

        const attrs = {
          class: 'mention tw:mention',
          'data-mention': modelAttributeValue.id,
        };

        if (modelAttributeValue.link) {
          attrs.href = modelAttributeValue.link;
        }
        if (modelAttributeValue.userId) {
          attrs['data-mentioned-user-id'] = String(modelAttributeValue.userId);
        }

        return writer.createAttributeElement('a', attrs, {
          priority: 20,
          id: modelAttributeValue.uid,
        });
      },
      converterPriority: 'high',
    });
  }

  function MentionCustomization(editor) {
    // Must be registered before data is loaded, otherwise initial data pipeline
    // uses built-in mention mapping for upcast/downcast.
    registerMentionUpcast(editor);
    registerMentionDowncast(editor);
  }

  function patchEditorCreate() {
    if (!window.ClassicEditor || typeof window.ClassicEditor.create !== 'function') {
      return;
    }
    if (window.ClassicEditor.__customMentionsPatched) {
      return;
    }

    const originalCreate = window.ClassicEditor.create.bind(window.ClassicEditor);
    window.ClassicEditor.create = (element, config = {}) => {
      const extraPlugins = ensureArray(config.extraPlugins);
      if (!extraPlugins.includes(MentionCustomization)) {
        extraPlugins.push(MentionCustomization);
      }

      return originalCreate(element, {
        ...config,
        extraPlugins,
      });
    };

    window.ClassicEditor.__customMentionsPatched = true;
  }

  function registerEditorExtensions(editor) {
    if (!editor || !editor.plugins) {
      return;
    }

    // Keep for editors initialized before our create() patch. Guard flags make this idempotent.
    registerMentionUpcast(editor);
    registerMentionDowncast(editor);
  }

  function patchExistingEditors() {
    if (!window.editors || typeof window.editors !== 'object') {
      return;
    }

    Object.values(window.editors).forEach((editor) => {
      registerEditorExtensions(editor);
    });
  }

  function registerCallbacks(root = document) {
    patchEditorCreate();

    if (typeof window.ckeditorRegisterCallback !== 'function') {
      return;
    }

    root.querySelectorAll('textarea.django_ckeditor_5').forEach((el) => {
      if (el.id) {
        window.ckeditorRegisterCallback(el.id, registerEditorExtensions);
      }
    });

    // Some editors may already be initialized before callbacks are registered.
    patchExistingEditors();
  }

  patchEditorCreate();
  document.addEventListener('DOMContentLoaded', () => registerCallbacks());

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1) {
          registerCallbacks(node);
        }
      });
    });
  });

  observer.observe(document.body, { childList: true, subtree: true });
})();
