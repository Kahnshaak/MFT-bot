/**
 * Mobile-specific enhancements for Game Night Bot Dashboard
 * Provides touch gestures, mobile UI optimizations, and PWA functionality
 */

class MobileEnhancements {
    constructor() {
        this.isTouch = 'ontouchstart' in window;
        this.isMobile = window.innerWidth <= 768;
        this.isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        this.isAndroid = /Android/.test(navigator.userAgent);
        this.isStandalone = window.matchMedia('(display-mode: standalone)').matches;
        
        this.init();
    }
    
    init() {
        if (this.isMobile) {
            this.setupMobileOptimizations();
            this.setupTouchGestures();
            this.setupPullToRefresh();
            this.setupSwipeNavigation();
            this.setupMobileKeyboard();
            this.setupOfflineDetection();
        }
        
        this.setupPWAFeatures();
        this.setupNotifications();
    }
    
    setupMobileOptimizations() {
        // Prevent zoom on input focus (iOS)
        this.preventZoomOnInputs();
        
        // Add touch feedback
        this.addTouchFeedback();
        
        // Optimize scrolling
        this.optimizeScrolling();
        
        // Handle orientation changes
        this.handleOrientationChange();
        
        // Setup viewport height fix
        this.setupViewportHeightFix();
        
        // Add mobile-specific classes
        document.body.classList.add('mobile-device');
        if (this.isIOS) document.body.classList.add('ios-device');
        if (this.isAndroid) document.body.classList.add('android-device');
    }
    
    preventZoomOnInputs() {
        const inputs = document.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            if (!input.style.fontSize || parseFloat(input.style.fontSize) < 16) {
                input.style.fontSize = '16px';
            }
        });
    }
    
    addTouchFeedback() {
        const touchElements = document.querySelectorAll('.btn, .nav-link, .dropdown-item, .card');
        
        touchElements.forEach(element => {
            element.addEventListener('touchstart', function(e) {
                this.style.transform = 'scale(0.95)';
                this.style.transition = 'transform 0.1s ease';
            }, { passive: true });
            
            element.addEventListener('touchend', function(e) {
                this.style.transform = '';
                this.style.transition = '';
            }, { passive: true });
            
            element.addEventListener('touchcancel', function(e) {
                this.style.transform = '';
                this.style.transition = '';
            }, { passive: true });
        });
    }
    
    optimizeScrolling() {
        // Enable momentum scrolling on iOS
        document.body.style.webkitOverflowScrolling = 'touch';
        
        // Optimize scroll performance
        let ticking = false;
        
        function updateScrollPosition() {
            // Update scroll-dependent elements
            const scrollTop = window.pageYOffset;
            const navbar = document.querySelector('.navbar');
            
            if (navbar) {
                if (scrollTop > 50) {
                    navbar.classList.add('scrolled');
                } else {
                    navbar.classList.remove('scrolled');
                }
            }
            
            ticking = false;
        }
        
        window.addEventListener('scroll', function() {
            if (!ticking) {
                requestAnimationFrame(updateScrollPosition);
                ticking = true;
            }
        }, { passive: true });
    }
    
    handleOrientationChange() {
        window.addEventListener('orientationchange', () => {
            setTimeout(() => {
                // Recalculate viewport dimensions
                this.setupViewportHeightFix();
                
                // Trigger resize event for charts and other components
                window.dispatchEvent(new Event('resize'));
                
                // Close any open dropdowns or modals
                const openDropdowns = document.querySelectorAll('.dropdown-menu.show');
                openDropdowns.forEach(dropdown => {
                    bootstrap.Dropdown.getInstance(dropdown.previousElementSibling)?.hide();
                });
            }, 100);
        });
    }
    
    setupViewportHeightFix() {
        // Fix for mobile browsers that change viewport height
        const vh = window.innerHeight * 0.01;
        document.documentElement.style.setProperty('--vh', `${vh}px`);
        
        // Update on resize
        window.addEventListener('resize', () => {
            const vh = window.innerHeight * 0.01;
            document.documentElement.style.setProperty('--vh', `${vh}px`);
        });
    }
    
    setupTouchGestures() {
        let startX, startY, startTime;
        
        document.addEventListener('touchstart', (e) => {
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
            startTime = Date.now();
        }, { passive: true });
        
        document.addEventListener('touchend', (e) => {
            if (!startX || !startY) return;
            
            const endX = e.changedTouches[0].clientX;
            const endY = e.changedTouches[0].clientY;
            const endTime = Date.now();
            
            const deltaX = endX - startX;
            const deltaY = endY - startY;
            const deltaTime = endTime - startTime;
            
            // Swipe detection
            if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 50 && deltaTime < 300) {
                if (deltaX > 0) {
                    this.handleSwipeRight();
                } else {
                    this.handleSwipeLeft();
                }
            }
            
            // Reset
            startX = startY = null;
        }, { passive: true });
    }
    
    handleSwipeRight() {
        // Open sidebar on swipe right
        const sidebar = document.querySelector('#sidebarOffcanvas');
        if (sidebar && !sidebar.classList.contains('show')) {
            const offcanvas = new bootstrap.Offcanvas(sidebar);
            offcanvas.show();
        }
    }
    
    handleSwipeLeft() {
        // Close sidebar on swipe left
        const sidebar = document.querySelector('#sidebarOffcanvas');
        if (sidebar && sidebar.classList.contains('show')) {
            const offcanvas = bootstrap.Offcanvas.getInstance(sidebar);
            if (offcanvas) offcanvas.hide();
        }
    }
    
    setupPullToRefresh() {
        let startY = 0;
        let currentY = 0;
        let pulling = false;
        
        const pullThreshold = 80;
        const maxPull = 120;
        
        document.addEventListener('touchstart', (e) => {
            if (window.scrollY === 0) {
                startY = e.touches[0].clientY;
            }
        }, { passive: true });
        
        document.addEventListener('touchmove', (e) => {
            if (startY === 0) return;
            
            currentY = e.touches[0].clientY;
            const pullDistance = currentY - startY;
            
            if (pullDistance > 0 && window.scrollY === 0) {
                e.preventDefault();
                
                const pullRatio = Math.min(pullDistance / maxPull, 1);
                const translateY = pullDistance * 0.5;
                
                document.body.style.transform = `translateY(${translateY}px)`;
                document.body.style.transition = 'none';
                
                if (pullDistance > pullThreshold && !pulling) {
                    pulling = true;
                    this.showPullToRefreshIndicator();
                } else if (pullDistance <= pullThreshold && pulling) {
                    pulling = false;
                    this.hidePullToRefreshIndicator();
                }
            }
        });
        
        document.addEventListener('touchend', () => {
            if (pulling) {
                this.triggerRefresh();
            }
            
            // Reset
            document.body.style.transform = '';
            document.body.style.transition = '';
            startY = 0;
            pulling = false;
            this.hidePullToRefreshIndicator();
        });
    }
    
    showPullToRefreshIndicator() {
        let indicator = document.querySelector('.pull-refresh-indicator');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.className = 'pull-refresh-indicator';
            indicator.innerHTML = '↓ Release to refresh';
            indicator.style.cssText = `
                position: fixed;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: var(--primary-color);
                color: white;
                padding: 0.5rem 1rem;
                border-radius: 2rem;
                font-size: 0.875rem;
                z-index: 9999;
                transition: opacity 0.3s ease;
            `;
            document.body.appendChild(indicator);
        }
        indicator.style.opacity = '1';
    }
    
    hidePullToRefreshIndicator() {
        const indicator = document.querySelector('.pull-refresh-indicator');
        if (indicator) {
            indicator.style.opacity = '0';
            setTimeout(() => indicator.remove(), 300);
        }
    }
    
    triggerRefresh() {
        // Show loading indicator
        this.showRefreshLoading();
        
        // Refresh page data
        setTimeout(() => {
            window.location.reload();
        }, 1000);
    }
    
    showRefreshLoading() {
        const loading = document.createElement('div');
        loading.className = 'refresh-loading';
        loading.innerHTML = `
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Refreshing...</span>
            </div>
            <div class="mt-2">Refreshing...</div>
        `;
        loading.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            padding: 2rem;
            border-radius: 1rem;
            box-shadow: 0 0.5rem 2rem rgba(0, 0, 0, 0.2);
            text-align: center;
            z-index: 9999;
        `;
        document.body.appendChild(loading);
    }
    
    setupSwipeNavigation() {
        // Add swipe navigation between pages
        const pages = [
            { path: '/', name: 'Dashboard' },
            { path: '/events', name: 'Events' },
            { path: '/users', name: 'Users' },
            { path: '/analytics', name: 'Analytics' }
        ];
        
        const currentPath = window.location.pathname;
        const currentIndex = pages.findIndex(page => page.path === currentPath);
        
        if (currentIndex !== -1) {
            // Add swipe indicators
            this.addSwipeIndicators(pages, currentIndex);
        }
    }
    
    addSwipeIndicators(pages, currentIndex) {
        const indicators = document.createElement('div');
        indicators.className = 'swipe-indicators mobile-only';
        indicators.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 0.5rem;
            background: rgba(0, 0, 0, 0.7);
            padding: 0.5rem 1rem;
            border-radius: 2rem;
            z-index: 1000;
        `;
        
        pages.forEach((page, index) => {
            const dot = document.createElement('div');
            dot.style.cssText = `
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: ${index === currentIndex ? 'white' : 'rgba(255, 255, 255, 0.5)'};
                transition: background 0.3s ease;
            `;
            indicators.appendChild(dot);
        });
        
        document.body.appendChild(indicators);
        
        // Auto-hide after 3 seconds
        setTimeout(() => {
            indicators.style.opacity = '0.3';
        }, 3000);
    }
    
    setupMobileKeyboard() {
        // Handle virtual keyboard appearance
        let initialViewportHeight = window.innerHeight;
        
        window.addEventListener('resize', () => {
            const currentHeight = window.innerHeight;
            const heightDifference = initialViewportHeight - currentHeight;
            
            if (heightDifference > 150) {
                // Keyboard is likely open
                document.body.classList.add('keyboard-open');
                
                // Scroll active input into view
                const activeElement = document.activeElement;
                if (activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')) {
                    setTimeout(() => {
                        activeElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }, 300);
                }
            } else {
                // Keyboard is likely closed
                document.body.classList.remove('keyboard-open');
            }
        });
    }
    
    setupOfflineDetection() {
        let offlineIndicator;
        
        const showOfflineIndicator = () => {
            if (!offlineIndicator) {
                offlineIndicator = document.createElement('div');
                offlineIndicator.className = 'offline-indicator';
                offlineIndicator.innerHTML = '📡 You are offline';
                offlineIndicator.style.cssText = `
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    background: linear-gradient(90deg, #f6c23e, #e74a3b);
                    color: white;
                    text-align: center;
                    padding: 0.5rem;
                    font-size: 0.875rem;
                    font-weight: 600;
                    z-index: 9999;
                    transform: translateY(-100%);
                    transition: transform 0.3s ease;
                `;
                document.body.appendChild(offlineIndicator);
            }
            
            setTimeout(() => {
                offlineIndicator.style.transform = 'translateY(0)';
            }, 100);
        };
        
        const hideOfflineIndicator = () => {
            if (offlineIndicator) {
                offlineIndicator.style.transform = 'translateY(-100%)';
                setTimeout(() => {
                    if (offlineIndicator) {
                        offlineIndicator.remove();
                        offlineIndicator = null;
                    }
                }, 300);
            }
        };
        
        window.addEventListener('offline', showOfflineIndicator);
        window.addEventListener('online', hideOfflineIndicator);
        
        // Check initial state
        if (!navigator.onLine) {
            showOfflineIndicator();
        }
    }
    
    setupPWAFeatures() {
        // Add to home screen prompt
        let deferredPrompt;
        
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            this.showInstallPrompt();
        });
        
        // Handle app installed
        window.addEventListener('appinstalled', () => {
            console.log('PWA was installed');
            this.hideInstallPrompt();
            this.showToast('App installed successfully!', 'success');
        });
        
        // Handle PWA launch
        if (this.isStandalone) {
            document.body.classList.add('pwa-mode');
            this.setupPWANavigation();
        }
    }
    
    showInstallPrompt() {
        if (this.isStandalone) return;
        
        const installBanner = document.createElement('div');
        installBanner.id = 'install-banner';
        installBanner.className = 'install-banner mobile-only';
        installBanner.innerHTML = `
            <div class="d-flex align-items-center justify-content-between p-3 bg-primary text-white">
                <div class="d-flex align-items-center">
                    <i class="bi bi-download me-2"></i>
                    <span>Install Game Night Bot for quick access</span>
                </div>
                <div>
                    <button class="btn btn-light btn-sm me-2" onclick="mobileEnhancements.installPWA()">
                        Install
                    </button>
                    <button class="btn btn-outline-light btn-sm" onclick="mobileEnhancements.hideInstallPrompt()">
                        ×
                    </button>
                </div>
            </div>
        `;
        
        document.body.insertBefore(installBanner, document.body.firstChild);
        
        // Auto-hide after 10 seconds
        setTimeout(() => {
            this.hideInstallPrompt();
        }, 10000);
    }
    
    hideInstallPrompt() {
        const banner = document.getElementById('install-banner');
        if (banner) {
            banner.remove();
        }
    }
    
    async installPWA() {
        const deferredPrompt = window.deferredPrompt;
        if (deferredPrompt) {
            deferredPrompt.prompt();
            const { outcome } = await deferredPrompt.userChoice;
            
            if (outcome === 'accepted') {
                console.log('User accepted PWA install');
            }
            
            window.deferredPrompt = null;
            this.hideInstallPrompt();
        }
    }
    
    setupPWANavigation() {
        // Add back button for PWA
        if (window.history.length > 1) {
            const backButton = document.createElement('button');
            backButton.className = 'btn btn-outline-primary btn-sm position-fixed';
            backButton.style.cssText = 'top: 70px; left: 10px; z-index: 1000; border-radius: 50%; width: 40px; height: 40px;';
            backButton.innerHTML = '<i class="bi bi-arrow-left"></i>';
            backButton.onclick = () => window.history.back();
            
            document.body.appendChild(backButton);
        }
    }
    
    setupNotifications() {
        if ('Notification' in window && 'serviceWorker' in navigator) {
            // Request permission on user interaction
            document.addEventListener('click', this.requestNotificationPermission.bind(this), { once: true });
        }
    }
    
    async requestNotificationPermission() {
        if (Notification.permission === 'default') {
            const permission = await Notification.requestPermission();
            
            if (permission === 'granted') {
                console.log('Notification permission granted');
                this.subscribeToNotifications();
                
                // Show welcome notification
                this.showNotification('Welcome!', {
                    body: 'You\'ll now receive notifications about game night updates.',
                    icon: '/static/icons/icon-192x192.png'
                });
            }
        }
    }
    
    async subscribeToNotifications() {
        try {
            const registration = await navigator.serviceWorker.ready;
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.urlBase64ToUint8Array('YOUR_VAPID_PUBLIC_KEY') // Replace with actual key
            });
            
            // Send subscription to server
            await fetch('/api/notifications/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': window.csrfToken
                },
                body: JSON.stringify(subscription)
            });
            
            console.log('Push notification subscription successful');
        } catch (error) {
            console.error('Push notification subscription failed:', error);
        }
    }
    
    showNotification(title, options = {}) {
        if (Notification.permission === 'granted') {
            const notification = new Notification(title, {
                icon: '/static/icons/icon-192x192.png',
                badge: '/static/icons/badge-72x72.png',
                vibrate: [100, 50, 100],
                ...options
            });
            
            // Auto-close after 5 seconds
            setTimeout(() => notification.close(), 5000);
            
            return notification;
        }
    }
    
    showToast(message, type = 'info', duration = 5000) {
        // Use the existing toast system from base.html
        if (window.showToast) {
            window.showToast(message, type, duration);
        }
    }
    
    urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');
        
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }
}

// Initialize mobile enhancements
const mobileEnhancements = new MobileEnhancements();

// Export for global access
window.mobileEnhancements = mobileEnhancements;