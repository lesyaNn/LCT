<#ftl output_format="plainText">
<#assign requiredActionsText><#if requiredActions??><#list requiredActions><#items as action>${msg("requiredAction.${action}")}<#sep>, </#sep></#items></#list></#if></#assign>
${msg("lctBrandName")}

${msg("executeActionsSubject")}

<#if ((user.firstName)!)?has_content>${msg("lctGreeting", user.firstName)}<#else>${msg("lctGreetingGeneric")}</#if>

${msg("lctActionsIntro")}
<#if requiredActionsText?has_content>${msg("lctActionsList", requiredActionsText)}
</#if>
${msg("lctActionsPrompt")}

${msg("lctCompleteSetup")}: ${link}

${msg("lctLimitedTime")}
${msg("lctFallbackText")}
${msg("lctIgnoreUnexpected")}
