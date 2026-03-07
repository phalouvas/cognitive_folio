# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from cognitive_folio.cognitive_folio.services.memory import CleanupMetricsStore, VectorMemory
from cognitive_folio.cognitive_folio.services.performance import IndexManagement
from cognitive_folio.cognitive_folio.services.settings_manager import SettingsManager
from cognitive_folio.cognitive_folio.services.web_search_service import WebSearchService

@frappe.whitelist()
def auto_fetch_portfolio_prices():
	"""
	Scheduled task to automatically fetch holdings data for portfolios with auth_fetch_prices enabled.
	Runs daily at 3:00 AM.
	"""
	try:
		# Get all portfolios with auth_fetch_prices enabled and not disabled
		portfolios = frappe.get_all(
			"CF Portfolio",
			filters=[
				["auth_fetch_prices", "=", 1],
				["disabled", "=", 0]
			],
			fields=["name", "portfolio_name"]
		)
		
		if not portfolios:
			frappe.logger().info("No portfolios found with auto fetch prices enabled")
			return
		
		total_portfolios = len(portfolios)
		updated_portfolios = 0
		
		frappe.logger().info(f"Starting auto price fetch for {total_portfolios} portfolios")
		
		for portfolio in portfolios:
			try:
				# Get the portfolio document
				portfolio_doc = frappe.get_doc("CF Portfolio", portfolio.name)
				
				# Call the fetch_holdings_data method without fundamentals
				result = portfolio_doc.fetch_holdings_data(with_fundamentals=False)
				
				if result and result > 0:
					updated_portfolios += 1
					frappe.logger().info(f"Successfully updated {result} holdings for portfolio: {portfolio.portfolio_name}")
				else:
					frappe.logger().info(f"No holdings to update for portfolio: {portfolio.portfolio_name}")
					
			except Exception as e:
				frappe.log_error(
					f"Error fetching prices for portfolio {portfolio.portfolio_name}: {str(e)}",
					"Auto Fetch Portfolio Prices Error"
				)
				continue
		
		frappe.logger().info(f"Auto price fetch completed. Updated {updated_portfolios} out of {total_portfolios} portfolios")
		
		# Commit the changes
		frappe.db.commit()
		
	except Exception as e:
		frappe.log_error(
			f"Error in auto_fetch_portfolio_prices scheduled task: {str(e)}",
			"Auto Fetch Portfolio Prices Task Error"
		)
@frappe.whitelist()
def auto_evaluate_holdings_news():
	"""
	Scheduled task to evaluate news for all holdings in portfolios with auth_fetch_prices enabled.
	Runs daily at 4:00 AM (1 hour after price fetch completes).
	"""
	try:
		# Get all portfolios with auth_fetch_prices enabled and not disabled
		portfolios = frappe.get_all(
			"CF Portfolio",
			filters=[
				["auth_fetch_prices", "=", 1],
				["disabled", "=", 0]
			],
			fields=["name", "portfolio_name"]
		)
		
		if not portfolios:
			frappe.logger().info("No portfolios found for news evaluation")
			return
		
		total_portfolios = len(portfolios)
		evaluated_portfolios = 0
		
		frappe.logger().info(f"Starting news evaluation for {total_portfolios} portfolios")
		
		for portfolio in portfolios:
			try:
				# Get the portfolio document
				portfolio_doc = frappe.get_doc("CF Portfolio", portfolio.name)
				
				frappe.logger().info(f"Starting news evaluation for portfolio: {portfolio.portfolio_name}")
				portfolio_doc.evaluate_holdings_news()
				evaluated_portfolios += 1
				frappe.logger().info(f"News evaluation queued for portfolio: {portfolio.portfolio_name}")
				
			except Exception as e:
				frappe.log_error(
					f"Error evaluating news for portfolio {portfolio.portfolio_name}: {str(e)}",
					"Auto Evaluate Holdings News Error"
				)
				continue
		
		frappe.logger().info(f"News evaluation completed for {evaluated_portfolios} out of {total_portfolios} portfolios")
		
		# Commit the changes
		frappe.db.commit()
		
	except Exception as e:
		frappe.log_error(
			f"Error in auto_evaluate_holdings_news scheduled task: {str(e)}",
			"Auto Evaluate Holdings News Task Error"
		)


@frappe.whitelist()
def cleanup_vector_memory_store():
	"""Scheduled cleanup for persistent vector memory retention."""
	metrics_store = CleanupMetricsStore()
	try:
		settings_doc = frappe.get_cached_doc("CF Settings")
		settings_manager = SettingsManager(settings_doc)
		config = settings_manager.get_memory_config()

		result = VectorMemory().prune_persistent_store(config=config)
		metrics_store.persist_daily(result)
		frappe.logger().info(
			f"Vector memory cleanup completed: pruned={result.get('pruned')} chats={result.get('chats')} deleted={result.get('deleted')}"
		)
		frappe.db.commit()
		return result
	except Exception as e:
		metrics_store.persist_daily({"pruned": False, "reason": "task_failed", "deleted": 0, "chats": 0})
		frappe.log_error(
			f"Error in cleanup_vector_memory_store scheduled task: {str(e)}",
			"Vector Memory Cleanup Task Error"
		)
		return {"pruned": False, "reason": "task_failed"}


@frappe.whitelist()
def capture_search_reliability_health_snapshot():
	"""Capture provider reliability and rate-limit health snapshot for operations visibility."""
	try:
		settings_doc = frappe.get_cached_doc("CF Settings")
		settings_manager = SettingsManager(settings_doc)
		performance_config = settings_manager.get_performance_config()
		if not performance_config.get("health_dashboard_enabled", True):
			return {"captured": False, "reason": "disabled"}

		service = WebSearchService(chat_message=type("_HealthProbe", (), {})())
		snapshot = service.get_health_snapshot()
		frappe.logger().info("Search reliability health snapshot: %s", frappe.as_json(snapshot))
		return {"captured": True, "providers": len((snapshot or {}).get("providers") or [])}
	except Exception as e:
		frappe.log_error(
			f"Error in capture_search_reliability_health_snapshot: {str(e)}",
			"Search Reliability Health Snapshot Error"
		)
		return {"captured": False, "reason": "task_failed"}


@frappe.whitelist()
def run_phase4_index_maintenance():
	"""Ensure common Phase 4 indexes exist for high-traffic chat and metrics tables."""
	try:
		settings_doc = frappe.get_cached_doc("CF Settings")
		settings_manager = SettingsManager(settings_doc)
		performance_config = settings_manager.get_performance_config()
		if not performance_config.get("db_index_maintenance_enabled", False):
			return {"ran": False, "reason": "disabled"}

		specs = [
			{
				"doctype": "CF Chat Message",
				"index_name": "idx_cf_chat_message_chat_creation",
				"columns": ["chat", "creation"],
			},
			{
				"doctype": "CF Tool Metric",
				"index_name": "idx_cf_tool_metric_date_tool",
				"columns": ["metric_date", "tool_name"],
			},
			{
				"doctype": "CF Vector Memory",
				"index_name": "idx_cf_vector_memory_chat_creation",
				"columns": ["chat", "creation"],
			},
		]

		result = IndexManagement().ensure_indexes(specs)
		frappe.db.commit()
		frappe.logger().info("Phase 4 index maintenance result: %s", frappe.as_json(result))
		return {"ran": True, "result": result}
	except Exception as e:
		frappe.log_error(
			f"Error in run_phase4_index_maintenance: {str(e)}",
			"Phase 4 Index Maintenance Error"
		)
		return {"ran": False, "reason": "task_failed"}
