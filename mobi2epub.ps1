param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)
& python -m mobi2epub.cli @Args
