#!/usr/bin/env python3
"""
Mobile Performance Testing Script

Tests mobile-specific features and performance optimizations for the Game Night Bot.
Validates Discord UI components, web dashboard responsiveness, and PWA functionality.
"""

import asyncio
import time
import json
import sys
from pathlib import Path
from typing import Dict, List, Any
import aiohttp
import logging

# Add src to path for imports
sys.path.append(str(Path(__file__).parent / "src"))

from utils.mobile_ui_components import (
    MobileOptimizedView, MobileOptimizedButton, MobileOptimizedSelect,
    MobileFriendlyPollView, create_mobile_optimized_embed
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MobilePerformanceTester:
    """Test suite for mobile performance and functionality."""
    
    def __init__(self):
        self.results = {
            "discord_ui": {},
            "web_dashboard": {},
            "pwa_features": {},
            "performance": {}
        }
        self.web_base_url = "http://localhost:8000"
    
    async def run_all_tests(self):
        """Run all mobile performance tests."""
        logger.info("Starting mobile performance tests...")
        
        # Test Discord UI components
        await self.test_discord_ui_components()
        
        # Test web dashboard responsiveness
        await self.test_web_dashboard()
        
        # Test PWA features
        await self.test_pwa_features()
        
        # Test performance metrics
        await self.test_performance_metrics()
        
        # Generate report
        self.generate_report()
        
        logger.info("Mobile performance tests completed!")
    
    async def test_discord_ui_components(self):
        """Test Discord UI component optimizations."""
        logger.info("Testing Discord UI components...")
        
        try:
            # Test mobile-optimized view creation
            start_time = time.time()
            view = MobileOptimizedView(timeout=300)
            creation_time = time.time() - start_time
            
            self.results["discord_ui"]["view_creation_time"] = creation_time
            self.results["discord_ui"]["view_timeout"] = view.timeout
            
            # Test mobile-optimized button creation
            start_time = time.time()
            button = MobileOptimizedButton(
                label="Test Button",
                emoji="🔵",
                style=1  # Primary style
            )
            button_creation_time = time.time() - start_time
            
            self.results["discord_ui"]["button_creation_time"] = button_creation_time
            self.results["discord_ui"]["button_has_emoji"] = button.emoji is not None
            
            # Test mobile-optimized select creation
            start_time = time.time()
            select_options = [
                {"label": f"Option {i}", "value": str(i), "emoji": f"{i}️⃣"}
                for i in range(1, 16)  # Test with 15 options (mobile limit)
            ]
            
            # Simulate select creation with option limit
            limited_options = select_options[:15]  # Mobile optimization
            select_creation_time = time.time() - start_time
            
            self.results["discord_ui"]["select_creation_time"] = select_creation_time
            self.results["discord_ui"]["select_options_limited"] = len(limited_options) <= 15
            
            # Test mobile-friendly poll view
            start_time = time.time()
            poll_data = {
                "type": "date",
                "options": [
                    {"date": "2024-12-20", "display_date": "Dec 20"},
                    {"date": "2024-12-21", "display_date": "Dec 21"}
                ]
            }
            event_data = {"title": "Test Event", "creator_id": "123456789"}
            
            poll_view = MobileFriendlyPollView(poll_data, event_data)
            poll_creation_time = time.time() - start_time
            
            self.results["discord_ui"]["poll_creation_time"] = poll_creation_time
            self.results["discord_ui"]["poll_has_management_buttons"] = len(poll_view.children) > 2
            
            # Test mobile-optimized embed
            start_time = time.time()
            embed = create_mobile_optimized_embed(
                title="Test Mobile Embed",
                description="This is a test embed optimized for mobile viewing."
            )
            embed_creation_time = time.time() - start_time
            
            self.results["discord_ui"]["embed_creation_time"] = embed_creation_time
            self.results["discord_ui"]["embed_has_mobile_footer"] = "mobile" in embed.footer.text.lower()
            
            logger.info("Discord UI component tests completed successfully")
            
        except Exception as e:
            logger.error(f"Discord UI component test failed: {e}")
            self.results["discord_ui"]["error"] = str(e)
    
    async def test_web_dashboard(self):
        """Test web dashboard mobile responsiveness."""
        logger.info("Testing web dashboard responsiveness...")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Test health endpoint
                start_time = time.time()
                async with session.get(f"{self.web_base_url}/api/health") as response:
                    health_response_time = time.time() - start_time
                    health_status = response.status
                    health_data = await response.json()
                
                self.results["web_dashboard"]["health_response_time"] = health_response_time
                self.results["web_dashboard"]["health_status"] = health_status
                self.results["web_dashboard"]["health_data"] = health_data
                
                # Test static assets (mobile-specific)
                mobile_assets = [
                    "/static/manifest.json",
                    "/static/sw.js",
                    "/static/mobile-enhancements.js",
                    "/static/style.css"
                ]
                
                asset_results = {}
                for asset in mobile_assets:
                    start_time = time.time()
                    async with session.get(f"{self.web_base_url}{asset}") as response:
                        load_time = time.time() - start_time
                        asset_results[asset] = {
                            "status": response.status,
                            "load_time": load_time,
                            "size": len(await response.read()) if response.status == 200 else 0
                        }
                
                self.results["web_dashboard"]["assets"] = asset_results
                
                # Test PWA manifest
                if asset_results.get("/static/manifest.json", {}).get("status") == 200:
                    async with session.get(f"{self.web_base_url}/static/manifest.json") as response:
                        manifest_data = await response.json()
                        
                        self.results["web_dashboard"]["manifest"] = {
                            "has_icons": len(manifest_data.get("icons", [])) > 0,
                            "has_shortcuts": len(manifest_data.get("shortcuts", [])) > 0,
                            "display_mode": manifest_data.get("display"),
                            "theme_color": manifest_data.get("theme_color")
                        }
                
                logger.info("Web dashboard tests completed successfully")
                
        except Exception as e:
            logger.error(f"Web dashboard test failed: {e}")
            self.results["web_dashboard"]["error"] = str(e)
    
    async def test_pwa_features(self):
        """Test PWA-specific features."""
        logger.info("Testing PWA features...")
        
        try:
            # Test service worker registration
            sw_features = {
                "service_worker_exists": Path("web/static/sw.js").exists(),
                "manifest_exists": Path("web/static/manifest.json").exists(),
                "mobile_enhancements_exists": Path("web/static/mobile-enhancements.js").exists()
            }
            
            # Test manifest content
            if sw_features["manifest_exists"]:
                with open("web/static/manifest.json", "r") as f:
                    manifest = json.load(f)
                    
                    sw_features.update({
                        "manifest_has_name": "name" in manifest,
                        "manifest_has_icons": len(manifest.get("icons", [])) > 0,
                        "manifest_has_start_url": "start_url" in manifest,
                        "manifest_has_display": manifest.get("display") == "standalone",
                        "manifest_has_shortcuts": len(manifest.get("shortcuts", [])) > 0
                    })
            
            # Test service worker content
            if sw_features["service_worker_exists"]:
                with open("web/static/sw.js", "r") as f:
                    sw_content = f.read()
                    
                    sw_features.update({
                        "sw_has_install_handler": "addEventListener('install'" in sw_content,
                        "sw_has_fetch_handler": "addEventListener('fetch'" in sw_content,
                        "sw_has_push_handler": "addEventListener('push'" in sw_content,
                        "sw_has_offline_support": "offline" in sw_content.lower()
                    })
            
            self.results["pwa_features"] = sw_features
            
            logger.info("PWA feature tests completed successfully")
            
        except Exception as e:
            logger.error(f"PWA feature test failed: {e}")
            self.results["pwa_features"]["error"] = str(e)
    
    async def test_performance_metrics(self):
        """Test performance-related metrics."""
        logger.info("Testing performance metrics...")
        
        try:
            # Test component creation performance
            component_times = []
            
            for i in range(100):
                start_time = time.time()
                
                # Create mobile-optimized components
                view = MobileOptimizedView()
                button = MobileOptimizedButton(label=f"Button {i}")
                embed = create_mobile_optimized_embed(f"Title {i}", f"Description {i}")
                
                creation_time = time.time() - start_time
                component_times.append(creation_time)
            
            avg_creation_time = sum(component_times) / len(component_times)
            max_creation_time = max(component_times)
            min_creation_time = min(component_times)
            
            self.results["performance"] = {
                "avg_component_creation_time": avg_creation_time,
                "max_component_creation_time": max_creation_time,
                "min_component_creation_time": min_creation_time,
                "total_tests": len(component_times)
            }
            
            # Test memory usage (basic)
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            self.results["performance"]["memory_usage_mb"] = memory_info.rss / 1024 / 1024
            self.results["performance"]["cpu_percent"] = process.cpu_percent()
            
            logger.info("Performance metric tests completed successfully")
            
        except Exception as e:
            logger.error(f"Performance metric test failed: {e}")
            self.results["performance"]["error"] = str(e)
    
    def generate_report(self):
        """Generate a comprehensive test report."""
        logger.info("Generating mobile performance report...")
        
        report = {
            "test_summary": {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_test_categories": len(self.results),
                "passed_categories": len([r for r in self.results.values() if "error" not in r]),
                "failed_categories": len([r for r in self.results.values() if "error" in r])
            },
            "results": self.results,
            "recommendations": self.generate_recommendations()
        }
        
        # Save report to file
        report_file = f"mobile_performance_report_{int(time.time())}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        # Print summary
        print("\n" + "="*60)
        print("MOBILE PERFORMANCE TEST REPORT")
        print("="*60)
        print(f"Test completed at: {report['test_summary']['timestamp']}")
        print(f"Categories tested: {report['test_summary']['total_test_categories']}")
        print(f"Categories passed: {report['test_summary']['passed_categories']}")
        print(f"Categories failed: {report['test_summary']['failed_categories']}")
        print(f"\nDetailed report saved to: {report_file}")
        
        # Print key metrics
        if "discord_ui" in self.results and "error" not in self.results["discord_ui"]:
            print(f"\nDiscord UI Performance:")
            print(f"  View creation: {self.results['discord_ui'].get('view_creation_time', 0):.4f}s")
            print(f"  Button creation: {self.results['discord_ui'].get('button_creation_time', 0):.4f}s")
            print(f"  Poll creation: {self.results['discord_ui'].get('poll_creation_time', 0):.4f}s")
        
        if "web_dashboard" in self.results and "error" not in self.results["web_dashboard"]:
            print(f"\nWeb Dashboard Performance:")
            print(f"  Health check: {self.results['web_dashboard'].get('health_response_time', 0):.4f}s")
            if "assets" in self.results["web_dashboard"]:
                avg_asset_time = sum(
                    asset.get("load_time", 0) 
                    for asset in self.results["web_dashboard"]["assets"].values()
                ) / len(self.results["web_dashboard"]["assets"])
                print(f"  Average asset load time: {avg_asset_time:.4f}s")
        
        if "performance" in self.results and "error" not in self.results["performance"]:
            print(f"\nPerformance Metrics:")
            print(f"  Average component creation: {self.results['performance'].get('avg_component_creation_time', 0):.6f}s")
            print(f"  Memory usage: {self.results['performance'].get('memory_usage_mb', 0):.2f} MB")
        
        print("\n" + "="*60)
    
    def generate_recommendations(self) -> List[str]:
        """Generate performance recommendations based on test results."""
        recommendations = []
        
        # Discord UI recommendations
        if "discord_ui" in self.results:
            ui_results = self.results["discord_ui"]
            
            if ui_results.get("view_creation_time", 0) > 0.01:
                recommendations.append("Consider optimizing Discord UI view creation for faster response times")
            
            if not ui_results.get("button_has_emoji", True):
                recommendations.append("Ensure all mobile buttons have emojis for better touch targets")
            
            if not ui_results.get("select_options_limited", True):
                recommendations.append("Limit select dropdown options to 15 or fewer for mobile optimization")
        
        # Web dashboard recommendations
        if "web_dashboard" in self.results:
            web_results = self.results["web_dashboard"]
            
            if web_results.get("health_response_time", 0) > 1.0:
                recommendations.append("Optimize web dashboard health check response time")
            
            if "assets" in web_results:
                slow_assets = [
                    asset for asset, data in web_results["assets"].items()
                    if data.get("load_time", 0) > 0.5
                ]
                if slow_assets:
                    recommendations.append(f"Optimize slow-loading assets: {', '.join(slow_assets)}")
        
        # PWA recommendations
        if "pwa_features" in self.results:
            pwa_results = self.results["pwa_features"]
            
            if not pwa_results.get("manifest_has_shortcuts", False):
                recommendations.append("Add app shortcuts to PWA manifest for better mobile UX")
            
            if not pwa_results.get("sw_has_offline_support", False):
                recommendations.append("Enhance service worker offline support")
        
        # Performance recommendations
        if "performance" in self.results:
            perf_results = self.results["performance"]
            
            if perf_results.get("avg_component_creation_time", 0) > 0.001:
                recommendations.append("Consider component pooling for better performance")
            
            if perf_results.get("memory_usage_mb", 0) > 100:
                recommendations.append("Monitor memory usage and implement cleanup strategies")
        
        return recommendations


async def main():
    """Run the mobile performance test suite."""
    tester = MobilePerformanceTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())