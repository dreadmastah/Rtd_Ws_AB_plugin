cmake_minimum_required(VERSION 3.20)
project(AstuCoreScaffold LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(astu_core INTERFACE)
target_include_directories(astu_core INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/common/include
    ${CMAKE_CURRENT_SOURCE_DIR}/trade_plugin/include
    ${CMAKE_CURRENT_SOURCE_DIR}/execution/include
    ${CMAKE_CURRENT_SOURCE_DIR}/wsrtd/include
    ${CMAKE_CURRENT_SOURCE_DIR}/ipc/include
    ${CMAKE_CURRENT_SOURCE_DIR}/account/include
    ${CMAKE_CURRENT_SOURCE_DIR}/instrument/include
)

if(WIN32)
    target_link_libraries(astu_core INTERFACE advapi32)
endif()

add_executable(astu_execution_sim execution/src/execution_sim_main.cpp)
target_link_libraries(astu_execution_sim PRIVATE astu_core)

add_executable(
    astu_sim_reconcile
    execution/src/simulation_reconcile_main.cpp
)
target_link_libraries(astu_sim_reconcile PRIVATE astu_core)

if(WIN32)
    add_executable(astu_execution_pipe_host execution/src/execution_pipe_host.cpp)
    target_link_libraries(
        astu_execution_pipe_host
        PRIVATE astu_core bcrypt winhttp
    )

    add_executable(astu_trade_pipe_smoke trade_plugin/src/execution_pipe_client_smoke.cpp)
    target_link_libraries(astu_trade_pipe_smoke PRIVATE astu_core)

    add_executable(
        astu_trade_pipe_live_smoke
        trade_plugin/src/live_execution_pipe_client_smoke.cpp
    )
    target_link_libraries(astu_trade_pipe_live_smoke PRIVATE astu_core)

    add_executable(
        astu_reconciliation_pipe_smoke
        trade_plugin/src/reconciliation_pipe_client_smoke.cpp
    )
    target_link_libraries(astu_reconciliation_pipe_smoke PRIVATE astu_core)

    add_library(
        astu_trade_amibroker
        SHARED
        trade_plugin/src/astu_trade_plugin.cpp
    )
    target_link_libraries(astu_trade_amibroker PRIVATE astu_core)
    set_target_properties(
        astu_trade_amibroker
        PROPERTIES
        OUTPUT_NAME "AstuTrade"
        PREFIX ""
    )

    add_executable(
        astu_trade_amibroker_exports_smoke
        trade_plugin/src/amibroker_plugin_exports_smoke.cpp
    )
    target_link_libraries(astu_trade_amibroker_exports_smoke PRIVATE astu_core)

    add_executable(
        astu_trade_amibroker_call_smoke
        trade_plugin/src/amibroker_plugin_call_smoke.cpp
    )
    target_link_libraries(astu_trade_amibroker_call_smoke PRIVATE astu_core)
endif()

enable_testing()
add_executable(astu_core_tests tests/core_sim_tests.cpp)
target_link_libraries(astu_core_tests PRIVATE astu_core)
add_test(NAME astu_core_tests COMMAND astu_core_tests)

add_executable(astu_instrument_sizing_tests tests/instrument_sizing_tests.cpp)
target_link_libraries(astu_instrument_sizing_tests PRIVATE astu_core)
add_test(NAME astu_instrument_sizing_tests COMMAND astu_instrument_sizing_tests)

add_executable(astu_position_state_tests tests/position_state_tests.cpp)
target_link_libraries(astu_position_state_tests PRIVATE astu_core)
add_test(NAME astu_position_state_tests COMMAND astu_position_state_tests)

add_executable(astu_order_fsm_tests tests/order_fsm_tests.cpp)
target_link_libraries(astu_order_fsm_tests PRIVATE astu_core)
add_test(NAME astu_order_fsm_tests COMMAND astu_order_fsm_tests)

add_executable(astu_reconciliation_tests tests/reconciliation_tests.cpp)
target_link_libraries(astu_reconciliation_tests PRIVATE astu_core)
add_test(NAME astu_reconciliation_tests COMMAND astu_reconciliation_tests)

add_executable(
    astu_startup_order_reconciliation_tests
    tests/startup_order_reconciliation_tests.cpp
)
target_link_libraries(
    astu_startup_order_reconciliation_tests
    PRIVATE astu_core
)
add_test(
    NAME astu_startup_order_reconciliation_tests
    COMMAND astu_startup_order_reconciliation_tests
)

add_executable(
    astu_runtime_order_reconciliation_tests
    tests/runtime_order_reconciliation_tests.cpp
)
target_link_libraries(
    astu_runtime_order_reconciliation_tests
    PRIVATE astu_core
)
add_test(
    NAME astu_runtime_order_reconciliation_tests
    COMMAND astu_runtime_order_reconciliation_tests
)

add_executable(
    astu_exposure_reservation_tests
    tests/exposure_reservation_tests.cpp
)
target_link_libraries(
    astu_exposure_reservation_tests
    PRIVATE astu_core
)
add_test(
    NAME astu_exposure_reservation_tests
    COMMAND astu_exposure_reservation_tests
)

add_executable(
    astu_account_loss_baseline_tests
    tests/account_loss_baseline_tests.cpp
)
target_link_libraries(
    astu_account_loss_baseline_tests
    PRIVATE astu_core
)
add_test(
    NAME astu_account_loss_baseline_tests
    COMMAND astu_account_loss_baseline_tests
)

add_executable(
    astu_realized_pnl_provider_tests
    tests/realized_pnl_provider_tests.cpp
)
target_link_libraries(
    astu_realized_pnl_provider_tests
    PRIVATE astu_core
)
add_test(
    NAME astu_realized_pnl_provider_tests
    COMMAND astu_realized_pnl_provider_tests
)

add_executable(
    astu_execution_status_tests
    tests/execution_status_tests.cpp
)
target_link_libraries(
    astu_execution_status_tests
    PRIVATE astu_core
)
add_test(
    NAME astu_execution_status_tests
    COMMAND astu_execution_status_tests
)

add_executable(
    astu_symbol_risk_status_tests
    tests/symbol_risk_status_tests.cpp
)
target_link_libraries(
    astu_symbol_risk_status_tests
    PRIVATE astu_core
)
add_test(
    NAME astu_symbol_risk_status_tests
    COMMAND astu_symbol_risk_status_tests
)

add_executable(
    astu_testnet_order_router_tests
    tests/testnet_order_router_tests.cpp
)
target_link_libraries(
    astu_testnet_order_router_tests
    PRIVATE astu_core
)
if(WIN32)
    target_link_libraries(
        astu_testnet_order_router_tests
        PRIVATE bcrypt winhttp
    )
endif()
add_test(
    NAME astu_testnet_order_router_tests
    COMMAND astu_testnet_order_router_tests
)

add_executable(
    astu_testnet_order_snapshot_tests
    tests/testnet_order_snapshot_tests.cpp
)
target_link_libraries(
    astu_testnet_order_snapshot_tests
    PRIVATE astu_core
)
if(WIN32)
    target_link_libraries(
        astu_testnet_order_snapshot_tests
        PRIVATE bcrypt winhttp
    )
endif()
add_test(
    NAME astu_testnet_order_snapshot_tests
    COMMAND astu_testnet_order_snapshot_tests
)

add_executable(
    astu_testnet_convergence_tests
    tests/testnet_convergence_tests.cpp
)
target_link_libraries(
    astu_testnet_convergence_tests
    PRIVATE astu_core
)
add_test(
    NAME astu_testnet_convergence_tests
    COMMAND astu_testnet_convergence_tests
)

if(WIN32)
    add_executable(
        astu_named_pipe_security_tests
        tests/named_pipe_security_tests.cpp
    )
    target_link_libraries(
        astu_named_pipe_security_tests
        PRIVATE astu_core
    )
    add_test(
        NAME astu_named_pipe_security_tests
        COMMAND astu_named_pipe_security_tests
    )

    add_test(
        NAME astu_trade_amibroker_exports
        COMMAND astu_trade_amibroker_exports_smoke $<TARGET_FILE:astu_trade_amibroker>
    )
endif()
