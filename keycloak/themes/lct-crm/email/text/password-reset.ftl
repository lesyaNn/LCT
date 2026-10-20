<#ftl output_format="plainText">
${msg("lctBrandName")}

${msg("passwordResetSubject")}

<#if ((user.firstName)!)?has_content>${msg("lctGreeting", user.firstName)}<#else>${msg("lctGreetingGeneric")}</#if>

${msg("lctResetIntro")}

${msg("lctResetPassword")}: ${link}

${msg("lctLimitedTime")}
${msg("lctFallbackText")}
${msg("lctResetSafety")}
