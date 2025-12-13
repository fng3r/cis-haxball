let currentSearchIndex = -1;
let searchResults = [];

function handleSearchKeydown(event) {
  const searchInput = event.target;
  const resultsContainer = document.getElementById('search-results');
  
  if (!resultsContainer || resultsContainer.children.length === 0) {
    return;
  }

  // Get all clickable search result links
  const resultLinks = resultsContainer.querySelectorAll('a[href]');
  searchResults = Array.from(resultLinks);

  if (searchResults.length === 0) {
    return;
  }

  switch (event.code) {
    case 'ArrowDown':
      event.preventDefault();
      currentSearchIndex = (currentSearchIndex + 1) % searchResults.length;
      highlightResult(currentSearchIndex);
      break;
    
    case 'ArrowUp':
      event.preventDefault();
      currentSearchIndex = currentSearchIndex <= 0 ? searchResults.length - 1 : currentSearchIndex - 1;
      highlightResult(currentSearchIndex);
      break;
    
    case 'Enter':
      if (currentSearchIndex >= 0 && currentSearchIndex < searchResults.length) {
        event.preventDefault();
        searchResults[currentSearchIndex].click();
      }
      break;
    
    case 'Escape':
      event.preventDefault();
      searchInput.value = '';
      resultsContainer.innerHTML = '';
      currentSearchIndex = -1;
      break;
  }
}

function hideSearchResults() {
    setTimeout(() => {
        const resultsContainer = $('#search-results');
        if (resultsContainer.length) {
          resultsContainer.hide();
        }
    }, 150);
}

function showSearchResults() {
    const resultsContainer = $('#search-results');
    if (resultsContainer.length) {
      resultsContainer.show();
    }
}

function highlightResult(index) {
  // Remove previous highlights
  searchResults.forEach(link => {
    link.classList.remove('tw:bg-primary', 'tw:text-primary-content');
  });

  // Highlight current result
  if (index >= 0 && index < searchResults.length) {
    const currentLink = searchResults[index];
    currentLink.classList.add('tw:bg-primary', 'tw:text-primary-content');
    
    // If it's the first result (index 0), scroll to the category header to show the title
    if (index === 0) {
      const categoryHeader = currentLink.closest('.category-container').querySelector('.category-header');
      if (categoryHeader) {
        categoryHeader.scrollIntoView({ block: 'nearest' });
      } else {
        currentLink.scrollIntoView({ block: 'nearest' });
      }
    } else {
      currentLink.scrollIntoView({ block: 'nearest' });
    }
  }
}

function setSelectedLink(element) {
  const index = searchResults.indexOf(element);
  if (index !== -1) {
    currentSearchIndex = index;
    highlightResult(currentSearchIndex);
  }
}

// Auto-select first result when search completes
document.addEventListener('htmx:afterRequest', function(event) {
  if (event.detail.target.id === 'search-results' && event.detail.successful) {
    currentSearchIndex = -1;
    const resultLinks = event.detail.target.querySelectorAll('a[href]');
    searchResults = Array.from(resultLinks);
    if (searchResults.length > 0) {
      currentSearchIndex = 0;
      highlightResult(0);
    }
    
    resultLinks.forEach(link => {
      link.addEventListener('mouseenter', function() {
        setSelectedLink(this);
      });
    });
  }
});

// Global keyboard shortcut to focus search input
document.addEventListener('keydown', function(event) {
  if ((event.ctrlKey || event.metaKey) && event.code === 'KeyI') {
    event.preventDefault();
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
      searchInput.focus();
    }
  }
});

document.addEventListener('DOMContentLoaded', function() {
  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.addEventListener('blur', hideSearchResults);
    searchInput.addEventListener('focus', showSearchResults);
    searchInput.addEventListener('keydown', handleSearchKeydown);
  }
}); 