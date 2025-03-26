// SPDX-License-Identifier: agpl-3.0
pragma solidity ^0.8.10;
import {IPool} from '../../interfaces/IPool.sol';
import {DataTypes} from '../../protocol/libraries/configuration/ReserveConfiguration.sol';

import {IERC20Metadata} from './IERC20Metadata.sol';
// import {ITransparentProxyFactory} from 'solidity-utils/contracts/transparent-proxy/interfaces/ITransparentProxyFactory.sol';
import {Ownable} from '../../dependencies/openzeppelin/contracts/Ownable.sol';

interface IStaticATokenFactory {
  /**
   * @notice Creates new staticATokens
   * @param underlyings the addresses of the underlyings to create.
   * @return address[] addresses of the new staticATokens.
   */
  function createStaticATokens(address[] memory underlyings) external returns (address[] memory);

  /**
   * @notice Returns all tokens deployed via this registry.
   * @return address[] list of tokens
   */
  function getStaticATokens() external view returns (address[] memory);

  /**
   * @notice Returns the staticAToken for a given underlying.
   * @param underlying the address of the underlying.
   * @return address the staticAToken address.
   */
  function getStaticAToken(address underlying) external view returns (address);
}
