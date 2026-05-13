#!/usr/bin/env python3
"""
Migration script from SQLite to PostgreSQL
This script exports data from SQLite and imports it to PostgreSQL
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import DictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def export_sqlite_data(db_path: str) -> List[Dict[str, Any]]:
    """Export all runs from SQLite database."""
    logger.info(f"Exporting data from SQLite: {db_path}")
    
    if not Path(db_path).exists():
        logger.error(f"SQLite database not found: {db_path}")
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM runs ORDER BY id")
        rows = cursor.fetchall()
        
        exported_data = []
        for row in rows:
            # Convert row to dict and handle JSON fields
            run_data = dict(row)
            
            # Parse extra_args from JSON string if present
            if run_data.get('extra_args'):
                try:
                    run_data['extra_args'] = json.loads(run_data['extra_args'])
                except json.JSONDecodeError:
                    run_data['extra_args'] = []
            else:
                run_data['extra_args'] = []
            
            # Convert boolean fields
            for bool_field in ['all_users', 'no_auto_provision', 'enforce_websocket_gates']:
                if bool_field in run_data:
                    run_data[bool_field] = bool(run_data[bool_field])
            
            # Handle post_order_actions
            if run_data.get('post_order_actions') is not None:
                run_data['post_order_actions'] = bool(run_data['post_order_actions'])
            
            # Convert timestamp strings to datetime objects
            for time_field in ['created_at', 'started_at', 'finished_at']:
                if run_data.get(time_field):
                    try:
                        # Handle SQLite timestamp format
                        ts_str = run_data[time_field]
                        if ts_str.endswith('Z'):
                            # ISO format with Z
                            run_data[time_field] = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        else:
                            # SQLite datetime format
                            run_data[time_field] = datetime.fromisoformat(ts_str)
                    except ValueError as e:
                        logger.warning(f"Could not parse timestamp {time_field}: {ts_str}, error: {e}")
                        run_data[time_field] = None
            
            exported_data.append(run_data)
        
        conn.close()
        logger.info(f"Exported {len(exported_data)} runs from SQLite")
        return exported_data
        
    except Exception as e:
        logger.error(f"Failed to export SQLite data: {e}")
        return []


def connect_postgres(connection_string: str) -> psycopg2.extensions.connection:
    """Connect to PostgreSQL database."""
    try:
        conn = psycopg2.connect(connection_string)
        conn.autocommit = False
        logger.info("Connected to PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise


def import_to_postgres(data: List[Dict[str, Any]], conn: psycopg2.extensions.connection):
    """Import data to PostgreSQL."""
    logger.info(f"Importing {len(data)} runs to PostgreSQL")
    
    try:
        with conn.cursor() as cursor:
            imported_count = 0
            skipped_count = 0
            
            for run_data in data:
                try:
                    # Check if run already exists
                    cursor.execute("SELECT id FROM runs WHERE id = %s", (run_data['id'],))
                    if cursor.fetchone():
                        skipped_count += 1
                        continue
                    
                    # Insert run data
                    insert_query = """
                    INSERT INTO runs (
                        id, flow, plan, timing, mode, store_id, phone, all_users, 
                        no_auto_provision, enforce_websocket_gates, post_order_actions, extra_args, status, 
                        command, created_at, started_at, finished_at, exit_code, 
                        log_path, report_path, story_path, events_path, error
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """
                    
                    cursor.execute(insert_query, (
                        run_data['id'],
                        run_data['flow'],
                        run_data['plan'],
                        run_data['timing'],
                        run_data.get('mode'),
                        run_data.get('store_id'),
                        run_data.get('phone'),
                        run_data['all_users'],
                        run_data['no_auto_provision'],
                        run_data.get('enforce_websocket_gates', False),
                        run_data.get('post_order_actions'),
                        json.dumps(run_data['extra_args']),
                        run_data['status'],
                        run_data['command'],
                        run_data['created_at'],
                        run_data.get('started_at'),
                        run_data.get('finished_at'),
                        run_data.get('exit_code'),
                        run_data.get('log_path'),
                        run_data.get('report_path'),
                        run_data.get('story_path'),
                        run_data.get('events_path'),
                        run_data.get('error')
                    ))
                    
                    imported_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to import run {run_data.get('id')}: {e}")
                    continue
            
            # Update the sequence to continue from the max ID
            if data:
                max_id = max(run['id'] for run in data)
                cursor.execute("SELECT setval('runs_id_seq', %s, true)", (max_id,))
                logger.info(f"Updated runs_id_seq to {max_id}")
            
            conn.commit()
            logger.info(f"Imported {imported_count} runs, skipped {skipped_count} existing runs")
            
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to import data to PostgreSQL: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(description='Migrate from SQLite to PostgreSQL')
    parser.add_argument('--sqlite-path', default='/workspace/simulate/runs/web-gui.sqlite',
                       help='Path to SQLite database')
    parser.add_argument('--postgres-url', 
                       default=os.getenv('DATABASE_URL', 'postgresql://simulator:simulator123@localhost:5432/simulator'),
                       help='PostgreSQL connection string')
    parser.add_argument('--dry-run', action='store_true',
                       help='Export data but don\'t import to PostgreSQL')
    
    args = parser.parse_args()
    
    # Export data from SQLite
    sqlite_data = export_sqlite_data(args.sqlite_path)
    
    if not sqlite_data:
        logger.error("No data to migrate")
        sys.exit(1)
    
    if args.dry_run:
        logger.info("Dry run - not importing to PostgreSQL")
        logger.info(f"Would import {len(sqlite_data)} runs")
        return
    
    # Import to PostgreSQL
    try:
        pg_conn = connect_postgres(args.postgres_url)
        import_to_postgres(sqlite_data, pg_conn)
        pg_conn.close()
        logger.info("Migration completed successfully")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
