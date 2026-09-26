#include <iostream>
#include <string>

#include "astu/ipc/named_pipe.hpp"

#ifdef _WIN32

namespace {

bool verify_current_user_only_descriptor() {
    astu::ipc::PipeSecurityAttributes security;

    BOOL dacl_present = FALSE;
    BOOL dacl_defaulted = FALSE;
    PACL dacl = nullptr;
    if (!GetSecurityDescriptorDacl(
            security.descriptor(),
            &dacl_present,
            &dacl,
            &dacl_defaulted)) {
        std::cerr << "GetSecurityDescriptorDacl failed error="
                  << GetLastError() << "\n";
        return false;
    }
    if (!dacl_present || dacl == nullptr || dacl_defaulted) {
        std::cerr << "expected explicit protected DACL\n";
        return false;
    }
    if (dacl->AceCount != 1) {
        std::cerr << "expected exactly one DACL ACE, got "
                  << dacl->AceCount << "\n";
        return false;
    }

    void* ace_raw = nullptr;
    if (!GetAce(dacl, 0, &ace_raw)) {
        std::cerr << "GetAce failed error=" << GetLastError() << "\n";
        return false;
    }

    const auto* header =
        static_cast<const ACE_HEADER*>(ace_raw);
    if (header->AceType != ACCESS_ALLOWED_ACE_TYPE) {
        std::cerr << "expected ACCESS_ALLOWED_ACE_TYPE\n";
        return false;
    }

    const auto* ace =
        static_cast<const ACCESS_ALLOWED_ACE*>(ace_raw);
    const PSID ace_sid = reinterpret_cast<PSID>(
        const_cast<DWORD*>(&ace->SidStart));

    const std::wstring allowed_sid =
        astu::ipc::sid_to_string(ace_sid);
    const std::wstring current_sid =
        astu::ipc::current_process_user_sid_string();
    if (allowed_sid != current_sid) {
        std::cerr << "DACL SID does not match current process user\n";
        return false;
    }
    if ((ace->Mask & GENERIC_ALL) == 0) {
        std::cerr << "current user ACE does not grant GENERIC_ALL\n";
        return false;
    }
    return true;
}

bool verify_anonymous_open_denied(const std::wstring& pipe_name) {
    auto pipe = astu::ipc::create_secure_named_pipe(pipe_name);

    if (!ImpersonateAnonymousToken(GetCurrentThread())) {
        std::cerr << "ImpersonateAnonymousToken failed error="
                  << GetLastError() << "\n";
        return false;
    }

    HANDLE client = CreateFileW(
        pipe_name.c_str(),
        GENERIC_READ | GENERIC_WRITE,
        0,
        nullptr,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        nullptr);
    const DWORD open_error =
        client == INVALID_HANDLE_VALUE ? GetLastError() : ERROR_SUCCESS;

    if (client != INVALID_HANDLE_VALUE) {
        CloseHandle(client);
    }
    if (!RevertToSelf()) {
        std::cerr << "RevertToSelf failed error="
                  << GetLastError() << "\n";
        return false;
    }

    if (client != INVALID_HANDLE_VALUE) {
        std::cerr << "anonymous token unexpectedly opened pipe\n";
        return false;
    }
    if (open_error != ERROR_ACCESS_DENIED) {
        std::cerr << "anonymous pipe open failed with unexpected error="
                  << open_error << "\n";
        return false;
    }
    return true;
}

}  // namespace

int main() {
    static_assert(
        (astu::ipc::kNamedPipeMode & PIPE_REJECT_REMOTE_CLIENTS) != 0,
        "remote Named Pipe clients must be rejected");
    static_assert(
        (astu::ipc::kNamedPipeOpenMode & FILE_FLAG_FIRST_PIPE_INSTANCE) != 0,
        "server must claim the first pipe instance");

    if (!verify_current_user_only_descriptor()) {
        return 1;
    }
    if (!verify_anonymous_open_denied(astu::ipc::kExecutionPipeName)) {
        return 2;
    }
    if (!verify_anonymous_open_denied(astu::ipc::kReconciliationPipeName)) {
        return 3;
    }

    std::cout << "NAMED_PIPE_CURRENT_USER_DACL=PASS\n";
    std::cout << "NAMED_PIPE_NON_OWNER_DENIED=PASS\n";
    std::cout << "NAMED_PIPE_REMOTE_REJECTION_FLAG=PASS\n";
    std::cout << "NAMED_PIPE_FIRST_INSTANCE=PASS\n";
    return 0;
}

#else

int main() {
    std::cerr << "Named Pipe security acceptance requires Windows.\n";
    return 2;
}

#endif
