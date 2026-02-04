/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { SupersetClient } from '@superset-ui/core';
import { ensureAppRoot } from 'src/utils/pathUtils';
import { safeStringify } from 'src/utils/safeStringify';

/**
 * Maximum SQL length that can be safely passed via URL query parameters.
 * URLs longer than ~2000 characters can cause issues with some servers/proxies.
 */
const MAX_URL_SQL_LENGTH = 2000;

export interface OpenSqlLabOptions {
  sql: string;
  dbid?: string | number;
  dbname?: string;
  name?: string;
  schema?: string;
  catalog?: string;
  autorun?: boolean;
  datasourceKey?: string;
  openInNewTab?: boolean;
}

/**
 * Opens SQL Lab with the provided SQL query.
 * Automatically uses POST for large SQL queries to avoid 414 errors.
 *
 * @param options - Configuration for opening SQL Lab
 */
export function openSqlLab(options: OpenSqlLabOptions): void {
  const { sql, openInNewTab = false, ...otherOptions } = options;

  // Use POST for large SQL queries to avoid 414 Request-URI Too Large errors
  const isLargeSql = sql.length > MAX_URL_SQL_LENGTH;

  if (isLargeSql || openInNewTab) {
    // Use POST form submission for large SQL or when opening in new tab
    const payload = {
      ...otherOptions,
      sql,
    };

    SupersetClient.postForm(ensureAppRoot('/sqllab/'), {
      form_data: safeStringify(payload),
    });
  } else {
    // For small SQL, use URL parameters (existing behavior)
    const queryParams = new URLSearchParams();
    if (otherOptions.dbid) {
      queryParams.set('dbid', String(otherOptions.dbid));
    }
    if (otherOptions.dbname) {
      queryParams.set('dbname', otherOptions.dbname);
    }
    if (sql) {
      queryParams.set('sql', sql);
    }
    if (otherOptions.name) {
      queryParams.set('name', otherOptions.name);
    }
    if (otherOptions.schema) {
      queryParams.set('schema', otherOptions.schema);
    }
    if (otherOptions.catalog) {
      queryParams.set('catalog', otherOptions.catalog);
    }
    if (otherOptions.autorun) {
      queryParams.set('autorun', 'true');
    }
    if (otherOptions.datasourceKey) {
      queryParams.set('datasourceKey', otherOptions.datasourceKey);
    }

    const url = `/sqllab/?${queryParams.toString()}`;
    if (openInNewTab) {
      window.open(url, '_blank', 'noopener,noreferrer');
    } else {
      window.location.href = url;
    }
  }
}
