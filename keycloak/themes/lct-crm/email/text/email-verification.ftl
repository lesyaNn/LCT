<#ftl output_format="plainText">
${msg("lctBrandName")}

${msg("emailVerificationSubject")}

<#if ((user.firstName)!)?has_content>${msg("lctGreeting", user.firstName)}<#else>${msg("lctGreetingGeneric")}</#if>

${msg("lctVerifyIntro")}

${msg("lctVerifyEmail")}: ${link}

${msg("lctLimitedTime")}
${msg("lctFallbackText")}
${msg("lctIgnoreUnexpected")}
