// Expo Metro 配置：让打包器能看到根目录的 shared/ 共享包
const { getDefaultConfig } = require('expo/metro-config')
const path = require('path')

const config = getDefaultConfig(__dirname)
config.watchFolders = [path.resolve(__dirname, '..', 'shared')]

module.exports = config
