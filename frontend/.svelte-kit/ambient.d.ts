
// this file is generated — do not edit it


/// <reference types="@sveltejs/kit" />

/**
 * This module provides access to environment variables that are injected _statically_ into your bundle at build time and are limited to _private_ access.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Static environment variables are [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env` at build time and then statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * **_Private_ access:**
 * 
 * - This module cannot be imported into client-side code
 * - This module only includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured)
 * 
 * For example, given the following build time environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { ENVIRONMENT, PUBLIC_BASE_URL } from '$env/static/private';
 * 
 * console.log(ENVIRONMENT); // => "production"
 * console.log(PUBLIC_BASE_URL); // => throws error during build
 * ```
 * 
 * The above values will be the same _even if_ different values for `ENVIRONMENT` or `PUBLIC_BASE_URL` are set at runtime, as they are statically replaced in your code with their build time values.
 */
declare module '$env/static/private' {
	export const ACC_PRODUCT_CONFIG_V3: string;
	export const ALLUSERSPROFILE: string;
	export const APPDATA: string;
	export const BASH_ENV: string;
	export const BRAVE_API_KEY: string;
	export const CARGO_HOME: string;
	export const CLAUDE_PROJECT_DIR: string;
	export const CLAUDE_SESSION_ID: string;
	export const CLIENT_INFO_IDE_TYPE: string;
	export const CLIENT_INFO_MACHINE_ID: string;
	export const CLIENT_INFO_PLATFORM: string;
	export const CLIENT_INFO_PLATFORM_VERSION: string;
	export const CLIENT_INFO_PLUGIN_NAME: string;
	export const CLIENT_INFO_PLUGIN_VERSION: string;
	export const CLIENT_INFO_PRODUCT_NAME: string;
	export const CLIENT_INFO_PRODUCT_VERSION: string;
	export const CLIENT_INFO_USER_AGENT_EXTENSION: string;
	export const CODEBUDDY_BUILTIN_SKILLS_DIR: string;
	export const CODEBUDDY_CODE_DISABLE_SESSION_SUMMARY: string;
	export const CODEBUDDY_CODE_EXPERIMENTAL_AGENT_TEAMS: string;
	export const CODEBUDDY_CODE_GIT_BASH_PATH: string;
	export const CODEBUDDY_CODE_IMAGE_COMPRESSION_MAX_DIMENSION: string;
	export const CODEBUDDY_CONFIG_DIR: string;
	export const CODEBUDDY_CONVERSATION_REQUEST_ID: string;
	export const CODEBUDDY_DISABLE_AUTO_MEMORY: string;
	export const CODEBUDDY_DISABLE_CRON: string;
	export const CODEBUDDY_DISABLE_EXTENDED_PLUGIN_HOOKS: string;
	export const CODEBUDDY_DISABLE_FORK_SUBAGENT: string;
	export const CODEBUDDY_DISABLE_IDE: string;
	export const CODEBUDDY_DISABLE_REQUEST_VALIDATION: string;
	export const CODEBUDDY_DISABLE_SESSION_HISTORY_CLEANUP: string;
	export const CODEBUDDY_DISABLE_SYSTEM_REMINDER_MD: string;
	export const CODEBUDDY_ENABLE_SECURITY_AUDIT: string;
	export const CODEBUDDY_GATEWAY_AUTH: string;
	export const CODEBUDDY_GATEWAY_DISABLE_API_DOCS: string;
	export const CODEBUDDY_GATEWAY_PASSWORD: string;
	export const CODEBUDDY_GIT_REPO_SCAN_DISABLED: string;
	export const CODEBUDDY_HIGH_CREDIT_APPROVAL_ENABLED: string;
	export const CODEBUDDY_HOST: string;
	export const CODEBUDDY_HOST_CAPABILITIES: string;
	export const CODEBUDDY_INCLUDE_TOPIC_MESSAGE: string;
	export const CODEBUDDY_INTERNET_ENVIRONMENT: string;
	export const CODEBUDDY_NODE_BIN: string;
	export const CODEBUDDY_PLUGIN_DIRS: string;
	export const CODEBUDDY_POWERSHELL_USE_PTY: string;
	export const CODEBUDDY_PROJECT_DIR: string;
	export const CODEBUDDY_PROMPT_SUGGESTION_DISABLED: string;
	export const CODEBUDDY_QIMEI36: string;
	export const CODEBUDDY_REASONING_ONLY_END_TURN: string;
	export const CODEBUDDY_REPLAY_SHOW_PRE_COMPACT: string;
	export const CODEBUDDY_SAFE_DELETE_BIN_DIR: string;
	export const CODEBUDDY_SAFE_DELETE_BULK_GUARD: string;
	export const CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR: string;
	export const CODEBUDDY_SAFE_DELETE_BULK_THRESHOLD: string;
	export const CODEBUDDY_SAFE_DELETE_REPORT_PATH: string;
	export const CODEBUDDY_SESSION_ID: string;
	export const CODEBUDDY_SKILL_TOOL_CHAR_BUDGET: string;
	export const CODEBUDDY_SKIP_GIT_BASH_CHECK: string;
	export const CODEBUDDY_TOOL_CALL_ID: string;
	export const COLOR: string;
	export const CommonProgramFiles: string;
	export const CommonProgramW6432: string;
	export const COMPUTERNAME: string;
	export const ComSpec: string;
	export const CUDA_PATH: string;
	export const CUDA_PATH_V12_3: string;
	export const DISABLE_AUTOUPDATER: string;
	export const DOTNET_SYSTEM_CONSOLE_USEUTF8ENCODING: string;
	export const dp0: string;
	export const DriverData: string;
	export const EDITOR: string;
	export const editor_sdk_port: string;
	export const EFC_9708: string;
	export const ELECTRON_RUN_AS_NODE: string;
	export const FPS_BROWSER_APP_PROFILE_STRING: string;
	export const FPS_BROWSER_USER_PROFILE_STRING: string;
	export const GALILEO_ENABLE: string;
	export const GALILEO_SDK_READY: string;
	export const GENIE_TRASH_DIR: string;
	export const HERMES_GIT_BASH_PATH: string;
	export const HERMES_HOME: string;
	export const HOME: string;
	export const HOMEDRIVE: string;
	export const HOMEPATH: string;
	export const INIT_CWD: string;
	export const JAVA_HOME: string;
	export const LANG: string;
	export const LOCALAPPDATA: string;
	export const LOGONSERVER: string;
	export const MX_APIKEY: string;
	export const NODE: string;
	export const NODE_ENV: string;
	export const NODE_EXE: string;
	export const NODE_OPTIONS: string;
	export const NO_PROXY: string;
	export const NPM_CLI_JS: string;
	export const npm_command: string;
	export const npm_config_cache: string;
	export const npm_config_globalconfig: string;
	export const npm_config_global_prefix: string;
	export const npm_config_init_module: string;
	export const npm_config_local_prefix: string;
	export const npm_config_node_gyp: string;
	export const npm_config_noproxy: string;
	export const npm_config_npm_version: string;
	export const npm_config_prefix: string;
	export const npm_config_userconfig: string;
	export const npm_config_user_agent: string;
	export const npm_execpath: string;
	export const npm_lifecycle_event: string;
	export const npm_lifecycle_script: string;
	export const npm_node_execpath: string;
	export const npm_package_json: string;
	export const npm_package_name: string;
	export const npm_package_version: string;
	export const NPM_PREFIX_JS: string;
	export const NPM_PREFIX_NPM_CLI_JS: string;
	export const NUMBER_OF_PROCESSORS: string;
	export const OneDrive: string;
	export const OneDriveConsumer: string;
	export const ORIGINAL_XDG_CURRENT_DESKTOP: string;
	export const OS: string;
	export const Path: string;
	export const PATHEXT: string;
	export const POWERSHELL_TELEMETRY_OPTOUT: string;
	export const PROCESSOR_ARCHITECTURE: string;
	export const PROCESSOR_IDENTIFIER: string;
	export const PROCESSOR_LEVEL: string;
	export const PROCESSOR_REVISION: string;
	export const PROG63E70B6F052: string;
	export const ProgramData: string;
	export const ProgramFiles: string;
	export const ProgramW6432: string;
	export const PROMPT: string;
	export const PSModulePath: string;
	export const PUBLIC: string;
	export const PyCharm: string;
	export const PYTHONPATH: string;
	export const RUSTUP_HOME: string;
	export const SERVER__HOST: string;
	export const SERVER__PORT: string;
	export const SESSIONNAME: string;
	export const SystemDrive: string;
	export const SystemRoot: string;
	export const TAURI_CLI_VERBOSITY: string;
	export const TAURI_ENV_ARCH: string;
	export const TAURI_ENV_DEBUG: string;
	export const TAURI_ENV_FAMILY: string;
	export const TAURI_ENV_PLATFORM: string;
	export const TAURI_ENV_PLATFORM_VERSION: string;
	export const TAURI_ENV_TARGET_TRIPLE: string;
	export const TEMP: string;
	export const TENCENT_DOCS_LOCAL_MCP: string;
	export const TENCENT_DOCS_LOCAL_SERVER: string;
	export const TERM: string;
	export const TMP: string;
	export const USERDOMAIN: string;
	export const USERDOMAIN_ROAMINGPROFILE: string;
	export const USERNAME: string;
	export const USERPROFILE: string;
	export const VITOICE_ENV: string;
	export const windir: string;
	export const WORKBUDDY_APPLICATION_NAME: string;
	export const WORKBUDDY_APP_NAME: string;
	export const WORKBUDDY_APP_PATH: string;
	export const WORKBUDDY_APP_VERSION: string;
	export const WORKBUDDY_CONFIG_DIR: string;
	export const WORKBUDDY_DATA_FOLDER_NAME: string;
	export const WORKBUDDY_EXTRA_PATHS: string;
	export const WORKBUDDY_FS_PROTECTION_ROLE: string;
	export const WORKBUDDY_IS_PACKAGED: string;
	export const WORKBUDDY_LEGACY_LOCALSTORAGE_MIGRATION_RESULT_PATH: string;
	export const WORKBUDDY_LOCALE: string;
	export const WORKBUDDY_MENU_LOCALE: string;
	export const WORKBUDDY_NODE_ENV: string;
	export const WORKBUDDY_PAC_RPC_SOCKET: string;
	export const WORKBUDDY_PAC_RPC_TOKEN: string;
	export const WORKBUDDY_PRODUCT_NAME: string;
	export const WORKBUDDY_PROMPT_TEMPLATES_DIR: string;
	export const WORKBUDDY_PROXY_SOURCE: string;
	export const WORKBUDDY_RESOURCES_PATH: string;
	export const WORKBUDDY_STARTUP_DATE: string;
	export const WORKBUDDY_STARTUP_PID: string;
	export const WORKBUDDY_STARTUP_TIME: string;
	export const WORKBUDDY_USER_DATA_DIR: string;
	export const _prog: string;
}

/**
 * This module provides access to environment variables that are injected _statically_ into your bundle at build time and are _publicly_ accessible.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Static environment variables are [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env` at build time and then statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * **_Public_ access:**
 * 
 * - This module _can_ be imported into client-side code
 * - **Only** variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`) are included
 * 
 * For example, given the following build time environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { ENVIRONMENT, PUBLIC_BASE_URL } from '$env/static/public';
 * 
 * console.log(ENVIRONMENT); // => throws error during build
 * console.log(PUBLIC_BASE_URL); // => "http://site.com"
 * ```
 * 
 * The above values will be the same _even if_ different values for `ENVIRONMENT` or `PUBLIC_BASE_URL` are set at runtime, as they are statically replaced in your code with their build time values.
 */
declare module '$env/static/public' {
	
}

/**
 * This module provides access to environment variables set _dynamically_ at runtime and that are limited to _private_ access.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Dynamic environment variables are defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`.
 * 
 * **_Private_ access:**
 * 
 * - This module cannot be imported into client-side code
 * - This module includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured)
 * 
 * > [!NOTE] In `dev`, `$env/dynamic` includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 * 
 * > [!NOTE] To get correct types, environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * >
 * > ```env
 * > MY_FEATURE_FLAG=
 * > ```
 * >
 * > You can override `.env` values from the command line like so:
 * >
 * > ```sh
 * > MY_FEATURE_FLAG="enabled" npm run dev
 * > ```
 * 
 * For example, given the following runtime environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { env } from '$env/dynamic/private';
 * 
 * console.log(env.ENVIRONMENT); // => "production"
 * console.log(env.PUBLIC_BASE_URL); // => undefined
 * ```
 */
declare module '$env/dynamic/private' {
	export const env: {
		ACC_PRODUCT_CONFIG_V3: string;
		ALLUSERSPROFILE: string;
		APPDATA: string;
		BASH_ENV: string;
		BRAVE_API_KEY: string;
		CARGO_HOME: string;
		CLAUDE_PROJECT_DIR: string;
		CLAUDE_SESSION_ID: string;
		CLIENT_INFO_IDE_TYPE: string;
		CLIENT_INFO_MACHINE_ID: string;
		CLIENT_INFO_PLATFORM: string;
		CLIENT_INFO_PLATFORM_VERSION: string;
		CLIENT_INFO_PLUGIN_NAME: string;
		CLIENT_INFO_PLUGIN_VERSION: string;
		CLIENT_INFO_PRODUCT_NAME: string;
		CLIENT_INFO_PRODUCT_VERSION: string;
		CLIENT_INFO_USER_AGENT_EXTENSION: string;
		CODEBUDDY_BUILTIN_SKILLS_DIR: string;
		CODEBUDDY_CODE_DISABLE_SESSION_SUMMARY: string;
		CODEBUDDY_CODE_EXPERIMENTAL_AGENT_TEAMS: string;
		CODEBUDDY_CODE_GIT_BASH_PATH: string;
		CODEBUDDY_CODE_IMAGE_COMPRESSION_MAX_DIMENSION: string;
		CODEBUDDY_CONFIG_DIR: string;
		CODEBUDDY_CONVERSATION_REQUEST_ID: string;
		CODEBUDDY_DISABLE_AUTO_MEMORY: string;
		CODEBUDDY_DISABLE_CRON: string;
		CODEBUDDY_DISABLE_EXTENDED_PLUGIN_HOOKS: string;
		CODEBUDDY_DISABLE_FORK_SUBAGENT: string;
		CODEBUDDY_DISABLE_IDE: string;
		CODEBUDDY_DISABLE_REQUEST_VALIDATION: string;
		CODEBUDDY_DISABLE_SESSION_HISTORY_CLEANUP: string;
		CODEBUDDY_DISABLE_SYSTEM_REMINDER_MD: string;
		CODEBUDDY_ENABLE_SECURITY_AUDIT: string;
		CODEBUDDY_GATEWAY_AUTH: string;
		CODEBUDDY_GATEWAY_DISABLE_API_DOCS: string;
		CODEBUDDY_GATEWAY_PASSWORD: string;
		CODEBUDDY_GIT_REPO_SCAN_DISABLED: string;
		CODEBUDDY_HIGH_CREDIT_APPROVAL_ENABLED: string;
		CODEBUDDY_HOST: string;
		CODEBUDDY_HOST_CAPABILITIES: string;
		CODEBUDDY_INCLUDE_TOPIC_MESSAGE: string;
		CODEBUDDY_INTERNET_ENVIRONMENT: string;
		CODEBUDDY_NODE_BIN: string;
		CODEBUDDY_PLUGIN_DIRS: string;
		CODEBUDDY_POWERSHELL_USE_PTY: string;
		CODEBUDDY_PROJECT_DIR: string;
		CODEBUDDY_PROMPT_SUGGESTION_DISABLED: string;
		CODEBUDDY_QIMEI36: string;
		CODEBUDDY_REASONING_ONLY_END_TURN: string;
		CODEBUDDY_REPLAY_SHOW_PRE_COMPACT: string;
		CODEBUDDY_SAFE_DELETE_BIN_DIR: string;
		CODEBUDDY_SAFE_DELETE_BULK_GUARD: string;
		CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR: string;
		CODEBUDDY_SAFE_DELETE_BULK_THRESHOLD: string;
		CODEBUDDY_SAFE_DELETE_REPORT_PATH: string;
		CODEBUDDY_SESSION_ID: string;
		CODEBUDDY_SKILL_TOOL_CHAR_BUDGET: string;
		CODEBUDDY_SKIP_GIT_BASH_CHECK: string;
		CODEBUDDY_TOOL_CALL_ID: string;
		COLOR: string;
		CommonProgramFiles: string;
		CommonProgramW6432: string;
		COMPUTERNAME: string;
		ComSpec: string;
		CUDA_PATH: string;
		CUDA_PATH_V12_3: string;
		DISABLE_AUTOUPDATER: string;
		DOTNET_SYSTEM_CONSOLE_USEUTF8ENCODING: string;
		dp0: string;
		DriverData: string;
		EDITOR: string;
		editor_sdk_port: string;
		EFC_9708: string;
		ELECTRON_RUN_AS_NODE: string;
		FPS_BROWSER_APP_PROFILE_STRING: string;
		FPS_BROWSER_USER_PROFILE_STRING: string;
		GALILEO_ENABLE: string;
		GALILEO_SDK_READY: string;
		GENIE_TRASH_DIR: string;
		HERMES_GIT_BASH_PATH: string;
		HERMES_HOME: string;
		HOME: string;
		HOMEDRIVE: string;
		HOMEPATH: string;
		INIT_CWD: string;
		JAVA_HOME: string;
		LANG: string;
		LOCALAPPDATA: string;
		LOGONSERVER: string;
		MX_APIKEY: string;
		NODE: string;
		NODE_ENV: string;
		NODE_EXE: string;
		NODE_OPTIONS: string;
		NO_PROXY: string;
		NPM_CLI_JS: string;
		npm_command: string;
		npm_config_cache: string;
		npm_config_globalconfig: string;
		npm_config_global_prefix: string;
		npm_config_init_module: string;
		npm_config_local_prefix: string;
		npm_config_node_gyp: string;
		npm_config_noproxy: string;
		npm_config_npm_version: string;
		npm_config_prefix: string;
		npm_config_userconfig: string;
		npm_config_user_agent: string;
		npm_execpath: string;
		npm_lifecycle_event: string;
		npm_lifecycle_script: string;
		npm_node_execpath: string;
		npm_package_json: string;
		npm_package_name: string;
		npm_package_version: string;
		NPM_PREFIX_JS: string;
		NPM_PREFIX_NPM_CLI_JS: string;
		NUMBER_OF_PROCESSORS: string;
		OneDrive: string;
		OneDriveConsumer: string;
		ORIGINAL_XDG_CURRENT_DESKTOP: string;
		OS: string;
		Path: string;
		PATHEXT: string;
		POWERSHELL_TELEMETRY_OPTOUT: string;
		PROCESSOR_ARCHITECTURE: string;
		PROCESSOR_IDENTIFIER: string;
		PROCESSOR_LEVEL: string;
		PROCESSOR_REVISION: string;
		PROG63E70B6F052: string;
		ProgramData: string;
		ProgramFiles: string;
		ProgramW6432: string;
		PROMPT: string;
		PSModulePath: string;
		PUBLIC: string;
		PyCharm: string;
		PYTHONPATH: string;
		RUSTUP_HOME: string;
		SERVER__HOST: string;
		SERVER__PORT: string;
		SESSIONNAME: string;
		SystemDrive: string;
		SystemRoot: string;
		TAURI_CLI_VERBOSITY: string;
		TAURI_ENV_ARCH: string;
		TAURI_ENV_DEBUG: string;
		TAURI_ENV_FAMILY: string;
		TAURI_ENV_PLATFORM: string;
		TAURI_ENV_PLATFORM_VERSION: string;
		TAURI_ENV_TARGET_TRIPLE: string;
		TEMP: string;
		TENCENT_DOCS_LOCAL_MCP: string;
		TENCENT_DOCS_LOCAL_SERVER: string;
		TERM: string;
		TMP: string;
		USERDOMAIN: string;
		USERDOMAIN_ROAMINGPROFILE: string;
		USERNAME: string;
		USERPROFILE: string;
		VITOICE_ENV: string;
		windir: string;
		WORKBUDDY_APPLICATION_NAME: string;
		WORKBUDDY_APP_NAME: string;
		WORKBUDDY_APP_PATH: string;
		WORKBUDDY_APP_VERSION: string;
		WORKBUDDY_CONFIG_DIR: string;
		WORKBUDDY_DATA_FOLDER_NAME: string;
		WORKBUDDY_EXTRA_PATHS: string;
		WORKBUDDY_FS_PROTECTION_ROLE: string;
		WORKBUDDY_IS_PACKAGED: string;
		WORKBUDDY_LEGACY_LOCALSTORAGE_MIGRATION_RESULT_PATH: string;
		WORKBUDDY_LOCALE: string;
		WORKBUDDY_MENU_LOCALE: string;
		WORKBUDDY_NODE_ENV: string;
		WORKBUDDY_PAC_RPC_SOCKET: string;
		WORKBUDDY_PAC_RPC_TOKEN: string;
		WORKBUDDY_PRODUCT_NAME: string;
		WORKBUDDY_PROMPT_TEMPLATES_DIR: string;
		WORKBUDDY_PROXY_SOURCE: string;
		WORKBUDDY_RESOURCES_PATH: string;
		WORKBUDDY_STARTUP_DATE: string;
		WORKBUDDY_STARTUP_PID: string;
		WORKBUDDY_STARTUP_TIME: string;
		WORKBUDDY_USER_DATA_DIR: string;
		_prog: string;
		[key: `PUBLIC_${string}`]: undefined;
		[key: `${string}`]: string | undefined;
	}
}

/**
 * This module provides access to environment variables set _dynamically_ at runtime and that are _publicly_ accessible.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Dynamic environment variables are defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`.
 * 
 * **_Public_ access:**
 * 
 * - This module _can_ be imported into client-side code
 * - **Only** variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`) are included
 * 
 * > [!NOTE] In `dev`, `$env/dynamic` includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 * 
 * > [!NOTE] To get correct types, environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * >
 * > ```env
 * > MY_FEATURE_FLAG=
 * > ```
 * >
 * > You can override `.env` values from the command line like so:
 * >
 * > ```sh
 * > MY_FEATURE_FLAG="enabled" npm run dev
 * > ```
 * 
 * For example, given the following runtime environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://example.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { env } from '$env/dynamic/public';
 * console.log(env.ENVIRONMENT); // => undefined, not public
 * console.log(env.PUBLIC_BASE_URL); // => "http://example.com"
 * ```
 * 
 * ```
 * 
 * ```
 */
declare module '$env/dynamic/public' {
	export const env: {
		[key: `PUBLIC_${string}`]: string | undefined;
	}
}
