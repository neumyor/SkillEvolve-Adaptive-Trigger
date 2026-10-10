# Skill artifacts

每个 Markdown 文件保存一个参与六元组测试的 skill 正文。六元组文件中的 `skill` 字段使用相对路径 `skill_files/<filename>.md`，可直接定位到对应文件。

`manifest.json` 记录每个文件的原始 skill 标识、来源文件、正文 SHA-256 和引用行数。相同短 key 在不同 run 中如果正文不同，会分别保存为不同文件。
