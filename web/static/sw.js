// Game Night Bot Dashboard Service Worker
// Provides offline functionality and caching for PWA

const CACHE_NAME = 'gamenight-dashboard-v1.0.0';
const STATIC_CACHE_NAME = 'gamenight-static-v1.0.0';
const DYNAMIC_CACHE_NAME = 'gamenight-dynamic-v1.0.0';

// Resources to cache immediately
const STATIC_ASSETS = [
  '/',
  '/static/style.css',
  '/static/manifest.json',
  '/auth/login',
  '/api/health',
  // Bootstrap CSS and JS
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
  // Bootstrap Icons
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css',
  // Font Awesome
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css'
];

// API endpoints that should be cached
const CACHEABLE_API_ENDPOINTS = [
  '/api/health',
  '/api/monitoring/dashboard',
  '/api/analytics/attendance',
  '/api/analytics/games'
];

// Install event - cache static assets
self.addEventListener('install', event => {
  console.log('Service Worker: Installing...');
  
  event.waitUntil(
    caches.open(STATIC_CACHE_NAME)
      .then(cache => {
        console.log('Service Worker: Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log('Service Worker: Static assets cached');
        return self.skipWaiting();
      })
      .catch(error => {
        console.error('Service Worker: Failed to cache static assets', error);
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  console.log('Service Worker: Activating...');
  
  event.waitUntil(
    caches.keys()
      .then(cacheNames => {
        return Promise.all(
          cacheNames.map(cacheName => {
            if (cacheName !== STATIC_CACHE_NAME && 
                cacheName !== DYNAMIC_CACHE_NAME &&
                cacheName !== CACHE_NAME) {
              console.log('Service Worker: Deleting old cache', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => {
        console.log('Service Worker: Activated');
        return self.clients.claim();
      })
  );
});

// Fetch event - serve from cache or network
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }
  
  // Skip Chrome extension requests
  if (url.protocol === 'chrome-extension:') {
    return;
  }
  
  // Handle different types of requests
  if (isStaticAsset(request)) {
    event.respondWith(handleStaticAsset(request));
  } else if (isAPIRequest(request)) {
    event.respondWith(handleAPIRequest(request));
  } else if (isPageRequest(request)) {
    event.respondWith(handlePageRequest(request));
  } else {
    event.respondWith(handleOtherRequest(request));
  }
});

// Check if request is for a static asset
function isStaticAsset(request) {
  const url = new URL(request.url);
  return url.pathname.startsWith('/static/') ||
         url.hostname === 'cdn.jsdelivr.net' ||
         url.hostname === 'cdnjs.cloudflare.com' ||
         STATIC_ASSETS.includes(url.pathname);
}

// Check if request is for an API endpoint
function isAPIRequest(request) {
  const url = new URL(request.url);
  return url.pathname.startsWith('/api/');
}

// Check if request is for a page
function isPageRequest(request) {
  const url = new URL(request.url);
  return request.headers.get('accept')?.includes('text/html');
}

// Handle static asset requests - cache first strategy
async function handleStaticAsset(request) {
  try {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.error('Service Worker: Failed to handle static asset', error);
    
    // Return offline fallback for critical assets
    if (request.url.includes('bootstrap') || request.url.includes('style.css')) {
      return new Response('/* Offline fallback styles */', {
        headers: { 'Content-Type': 'text/css' }
      });
    }
    
    throw error;
  }
}

// Handle API requests - network first with cache fallback
async function handleAPIRequest(request) {
  const url = new URL(request.url);
  
  try {
    // Always try network first for API requests
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok && CACHEABLE_API_ENDPOINTS.some(endpoint => 
        url.pathname.startsWith(endpoint))) {
      // Cache successful responses for specific endpoints
      const cache = await caches.open(DYNAMIC_CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('Service Worker: Network failed for API request, trying cache');
    
    // Try to serve from cache
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      // Add offline indicator header
      const response = cachedResponse.clone();
      response.headers.set('X-Served-From', 'cache');
      return response;
    }
    
    // Return offline response for health check
    if (url.pathname === '/api/health') {
      return new Response(JSON.stringify({
        status: 'offline',
        timestamp: new Date().toISOString(),
        message: 'Service Worker: Offline mode'
      }), {
        headers: { 
          'Content-Type': 'application/json',
          'X-Served-From': 'service-worker'
        }
      });
    }
    
    // Return generic offline response
    return new Response(JSON.stringify({
      error: 'Offline',
      message: 'This feature requires an internet connection'
    }), {
      status: 503,
      headers: { 
        'Content-Type': 'application/json',
        'X-Served-From': 'service-worker'
      }
    });
  }
}

// Handle page requests - network first with offline fallback
async function handlePageRequest(request) {
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      // Cache successful page responses
      const cache = await caches.open(DYNAMIC_CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('Service Worker: Network failed for page request, trying cache');
    
    // Try to serve from cache
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Serve offline page
    return getOfflinePage();
  }
}

// Handle other requests
async function handleOtherRequest(request) {
  try {
    return await fetch(request);
  } catch (error) {
    console.log('Service Worker: Network failed for other request');
    throw error;
  }
}

// Generate offline page
function getOfflinePage() {
  const offlineHTML = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Offline - Game Night Bot Dashboard</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #4e73df, #36b9cc);
                color: white;
                text-align: center;
                padding: 20px;
            }
            .offline-container {
                max-width: 400px;
                background: rgba(255, 255, 255, 0.1);
                padding: 2rem;
                border-radius: 1rem;
                backdrop-filter: blur(10px);
            }
            .offline-icon {
                font-size: 4rem;
                margin-bottom: 1rem;
            }
            .offline-title {
                font-size: 1.5rem;
                margin-bottom: 1rem;
                font-weight: bold;
            }
            .offline-message {
                margin-bottom: 2rem;
                opacity: 0.9;
            }
            .retry-button {
                background: rgba(255, 255, 255, 0.2);
                border: 2px solid rgba(255, 255, 255, 0.3);
                color: white;
                padding: 0.75rem 1.5rem;
                border-radius: 0.5rem;
                cursor: pointer;
                font-size: 1rem;
                transition: all 0.3s ease;
            }
            .retry-button:hover {
                background: rgba(255, 255, 255, 0.3);
                transform: translateY(-2px);
            }
            .cached-data {
                margin-top: 2rem;
                padding: 1rem;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 0.5rem;
                font-size: 0.9rem;
            }
        </style>
    </head>
    <body>
        <div class="offline-container">
            <div class="offline-icon">🎮</div>
            <div class="offline-title">You're Offline</div>
            <div class="offline-message">
                Game Night Bot Dashboard is currently unavailable. 
                Check your internet connection and try again.
            </div>
            <button class="retry-button" onclick="window.location.reload()">
                Try Again
            </button>
            <div class="cached-data">
                <strong>Offline Features:</strong><br>
                • View cached dashboard data<br>
                • Browse previously loaded pages<br>
                • Access help documentation
            </div>
        </div>
        
        <script>
            // Auto-retry when online
            window.addEventListener('online', () => {
                window.location.reload();
            });
            
            // Show connection status
            function updateConnectionStatus() {
                if (navigator.onLine) {
                    document.querySelector('.offline-message').innerHTML = 
                        'Connection restored! Refreshing...';
                    setTimeout(() => window.location.reload(), 1000);
                }
            }
            
            window.addEventListener('online', updateConnectionStatus);
            window.addEventListener('offline', updateConnectionStatus);
        </script>
    </body>
    </html>
  `;
  
  return new Response(offlineHTML, {
    headers: { 
      'Content-Type': 'text/html',
      'X-Served-From': 'service-worker'
    }
  });
}

// Background sync for failed requests
self.addEventListener('sync', event => {
  console.log('Service Worker: Background sync triggered', event.tag);
  
  if (event.tag === 'background-sync') {
    event.waitUntil(doBackgroundSync());
  }
});

async function doBackgroundSync() {
  console.log('Service Worker: Performing background sync');
  
  try {
    // Retry failed API requests
    const cache = await caches.open(DYNAMIC_CACHE_NAME);
    const requests = await cache.keys();
    
    for (const request of requests) {
      if (isAPIRequest(request)) {
        try {
          const response = await fetch(request);
          if (response.ok) {
            await cache.put(request, response.clone());
          }
        } catch (error) {
          console.log('Service Worker: Failed to sync request', request.url);
        }
      }
    }
  } catch (error) {
    console.error('Service Worker: Background sync failed', error);
  }
}

// Push notification handling
self.addEventListener('push', event => {
  console.log('Service Worker: Push notification received');
  
  const options = {
    body: 'You have new game night updates!',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'explore',
        title: 'View Dashboard',
        icon: '/static/icons/action-dashboard.png'
      },
      {
        action: 'close',
        title: 'Close',
        icon: '/static/icons/action-close.png'
      }
    ]
  };
  
  if (event.data) {
    const data = event.data.json();
    options.body = data.body || options.body;
    options.title = data.title || 'Game Night Bot';
    options.data = { ...options.data, ...data };
  }
  
  event.waitUntil(
    self.registration.showNotification('Game Night Bot', options)
  );
});

// Notification click handling
self.addEventListener('notificationclick', event => {
  console.log('Service Worker: Notification clicked', event.action);
  
  event.notification.close();
  
  if (event.action === 'explore') {
    event.waitUntil(
      clients.openWindow('/')
    );
  } else if (event.action === 'close') {
    // Just close the notification
    return;
  } else {
    // Default action - open dashboard
    event.waitUntil(
      clients.openWindow('/')
    );
  }
});

// Message handling from main thread
self.addEventListener('message', event => {
  console.log('Service Worker: Message received', event.data);
  
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'GET_VERSION') {
    event.ports[0].postMessage({ version: CACHE_NAME });
  }
});

console.log('Service Worker: Loaded successfully');